import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid
import heapq
from available import Available
from event import Event

import json
import logging

# Date handling 
import arrow # Replacement for datetime, based on moment.js
# import datetime # But we still need time
from dateutil import tz  # For interpreting local times


# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

###
# Globals
###
import config
if __name__ == "__main__":
    CONFIG = config.configuration()
else:
    CONFIG = config.configuration(proxied=True)

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.SECRET_KEY

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'
EVENTS = [] #Global container to hold events, eventually will be Database

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  if 'begin_date' not in flask.session:
    init_session_values()
  return render_template('index.html')

@app.route("/choose")
def choose():
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(service)
    return render_template('choose_cals.html')


@app.route("/choose_events", methods=['POST'])
def choose_events():
    global EVENTS
    ## For each calendar, print the events in date and time order
    app.logger.debug("Finding Events for each Calendar")

    ## Make sure we still have access to the account
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))
    service = get_gcal_service(credentials)

    # Get the list of calendars to include from the html form
    calendars = flask.request.form.getlist('include')
    
    # Returns a list of dateTime ranges to look through for overlap
    day_ranges = get_dateTime_list()
   
    time_min = arrow.get(flask.session['begin_date']).floor('day')
    time_max = arrow.get(flask.session['end_date']).ceil('day')
    
    EVENTS = [] 
    flask.g.events = []
    for calendar in calendars:
        # Calls a function that returns a list of events
        calendar = service.calendars().get(calendarId=calendar).execute()
        list_events = service.events().list(calendarId=calendar['id'],
                                            singleEvents=True,
                                            timeMin=time_min, timeMax=time_max).execute()['items']
        for i in range(len(list_events)):
            transparent = True
            # Check if event is marked as available
            if 'transparency' not in list_events[i]:
                transparent = False
            elif list_events[i]['transparency'] == 'opaque':
                transparent = False

            # Only do this if 'busy' event
            if not transparent:
                # 'date' only there if all day event
                if 'date' in list_events[i]['start']:
                    # all day event
                    event_start_time = arrow.get(list_events[i]['start']['date']).floor('day')
                    event_end_time = arrow.get(list_events[i]['start']['date']).ceil('day')
                else:
                    # normal event
                    event_start_time = arrow.get(list_events[i]['start']['dateTime'])
                    event_end_time = arrow.get(list_events[i]['end']['dateTime'])
                for date_range in day_ranges:
                    # Check if any part of an event overlaps
                    # Note: date/time range is not inclusive (using strict inequalities)
                    if date_range[0] < event_start_time < date_range[1] or \
                       date_range[0] < event_end_time < date_range[1] or \
                       (date_range[0] >= event_start_time and date_range[1] <= event_end_time):
                        
                        # make sure it's not being added twice
                        if list_events[i] in EVENTS:
                            continue
                        else:
                            EVENTS.append(list_events[i])

    # call a function that sorts the entire list of events by start date and time
    # and returns a printable string for the html page
    sort_events()
    flask.g.events = EVENTS
    
    # render a new html page "show_events" that lists the events in order
    # I did this instead of rendering on the index page. I thought it was cleaner
    return render_template('choose_events.html')


@app.route("/show_available", methods=['POST'])
def show_available():
    """
    Shows times the user is available within the given date time range
    """
    global EVENTS
    ## Make sure we still have access to the account
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))
    service = get_gcal_service(credentials)

    flask.g.available = []
    A = Available(flask.session['begin_date'], flask.session['end_date'],
                  get_flask_times())

    ignore_events = flask.request.form.getlist('ignore')
    for event in EVENTS:
        if not event.id in ignore_events:
            for i in range(len(A.time)):
                if event.start <= A.time[i] < event.end:
                    A.available[i] = False
    i = 0
    started = False
    while i < len(A.time):
        if i == len(A.time)-1:
            if started:
                end_range = A.time[i]
                started = False
                flask.g.available.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        else:
            if not started:
                if A.time[i].shift(minutes=+15) == A.time[i+1] and A.available[i]:
                    start_range = A.time[i]
                    started = True
            else:
                if not A.time[i].shift(minutes=+15) == A.time[i+1] or not A.available[i]:
                    end_range = A.time[i]
                    started = False
                    flask.g.available.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        i+=1
    return render_template('free_times.html')


def get_dateTime_list():
    """
    Returns a list of tuples that are start and end times for
    each acceptable chunk in the date range
    """
    b_hour, b_minute, e_hour, e_minute = get_flask_times()
    start_day = arrow.get(flask.session['begin_date'])
    end_day = arrow.get(flask.session['end_date']).ceil('day')
    start_day = start_day.replace(tzinfo='US/Pacific')
    end_day = end_day.replace(tzinfo='US/Pacific')
    
    #Set the first time range
    start_time = start_day.replace(hour=b_hour, minute=b_minute)
    end_time = start_day.replace(hour=e_hour, minute=e_minute)

    #Set the ultimate end day and time
    end_day = end_day.replace(hour=e_hour, minute=e_minute)
    
    day_ranges = []
    if start_time >= end_time:
        end_time = end_time.shift(days=+1)
        end_day = end_day.shift(days=+1)
    while start_time < end_day:
        day_ranges.append((start_time, end_time))
        start_time = start_time.shift(days=+1)
        end_time = end_time.shift(days=+1)
    return day_ranges

def get_flask_times():
    """
    Returns the integer versions of the time session objects as hour and minute
    """
    b_hour = int(to_24(flask.session['begin_time'])[:2])
    b_minute = int(to_24(flask.session['begin_time'])[-2:])
    e_hour = int(to_24(flask.session['end_time'])[:2])
    e_minute = int(to_24(flask.session['end_time'])[-2:])
    return [b_hour, b_minute, e_hour, e_minute]



####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service


def sort_events():
    """
    Sort events using a priority queue
    """
    global EVENTS
    H = []
    for event in EVENTS:
        if 'date' in event['start']:
            E = Event(arrow.get(event['start']['date']).floor('day'),
                 arrow.get(event['start']['date']).ceil('day'),
                 event['summary'], event['id'])
        else:
            E = Event(arrow.get(event['start']['dateTime']),
                 arrow.get(event['end']['dateTime']),
                 event['summary'], event['id'])
        heapq.heappush(H, E)
    EVENTS = []
    while H:
        EVENTS.append(heapq.heappop(H))

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('choose'))

#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use. 
#
#####

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    daterange = request.form.get('daterange')
    flask.session['begin_time'] = request.form.get('earliest')
    flask.session['end_time'] = request.form.get('latest')
    flask.session['daterange'] = daterange
    daterange_parts = daterange.split()
    flask.session['begin_date'] = interpret_date(daterange_parts[0])
    flask.session['end_date'] = interpret_date(daterange_parts[2])
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1], 
      flask.session['begin_date'], flask.session['end_date']))
    return flask.redirect(flask.url_for("choose"))


#convert from 12hr to 24hr time
def to_24(time):
    hour = time[0:2]
    minute = time[3:5]
    am_pm = time[6:8]
    if not hour == '12' and am_pm == 'PM':
        hour = str(int(hour)+12)
    elif hour == '12' and am_pm == 'AM':
        hour='00'
    return str(hour) + ":" + minute


####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = "09:00 AM"
    flask.session["end_time"] = "05:00 PM"

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        as_arrow = as_arrow.replace(year=2016) #HACK see below
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()
    #HACK #Workaround
    # isoformat() on raspberry Pi does not work for some dates
    # far from now.  It will fail with an overflow from time stamp out
    # of range while checking for daylight savings time.  Workaround is
    # to force the date-time combination into the year 2016, which seems to
    # get the timestamp into a reasonable range. This workaround should be
    # removed when Arrow or Dateutil.tz is fixed.
    # FIXME: Remove the workaround when arrow is fixed (but only after testing
    # on raspberry Pi --- failure is likely due to 32-bit integers on that platform)


def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        

        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])


#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    
