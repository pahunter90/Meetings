import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid
import heapq
from available import Available
from event import Event
import random

import json
import logging

# Date handling 
import arrow # Replacement for datetime, based on moment.js
# import datetime # But we still need time
from dateutil import tz  # For interpreting local times

# Mongo database
import pymongo
from pymongo import MongoClient

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


MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(
    CONFIG.ADMIN_USER,
    CONFIG.ADMIN_PW,
    CONFIG.DB_HOST, 
    CONFIG.DB_PORT, 
    CONFIG.DB)



####
# Database connection per server process
###

try: 
    dbclient = MongoClient(MONGO_CLIENT_URL)
    db = getattr(dbclient, CONFIG.DB)
    meetings = db.meetings

except:
    print("Failure opening database.  Is Mongo running? Correct password?")
    sys.exit(1)

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

#############################
#
#  Pages (routed from URLs)
#
#############################

#Index asks the user for their email address to login
#this would also include a password in a more perfect world
@app.route("/")
@app.route("/index")
def index():
    app.logger.debug("Entering index")
    if 'begin_date' not in flask.session:
        init_session_values()
    return render_template('index.html')


# After the user logs in force authentication through Google
# then show them their busy times if any
# and give them the option to edit busy times (if in a meeting)
# or create a meeting
@app.route("/login")
def login():
    if len(flask.request.args) == 2:
        login_email = flask.request.args.get('email')
        meeting_code = int(flask.request.args.get('code'))
    else:
        login_email = flask.session['login_email']
        meeting_code = int(flask.session['meeting_code'])
    meeting = meetings.find_one({'code': meeting_code})

    # No Meeting Exists
    if meeting is None:
        flask.flash('Invalid Meeting Code')
        return render_template('index.html')

    i = find_user_index(meeting, login_email) # -1 if not there
    
    # If not invited
    if i == -1:
        flask.flash('That email is not invited to that meeting')
        return render_template('index.html') 
    
    # Check for availablity
    if meeting['users'][i]['responded']:
        flask.g.available = find_availability(meeting, login_email)

    # Check for admin status
    if meeting['admin'] == login_email:
        flask.g.admin = True
        flask.g.available_times, flask.g.not_responded = meeting_availability(meeting)
        flask.g.code = meeting_code
    flask.session['login_email'] = login_email
    flask.session['meeting_code'] = meeting_code
    return render_template('login_page.html')


@app.route("/_delete")
def delete():
    meetings.remove({'code': int(flask.session['meeting_code'])})
    return flask.redirect(flask.url_for('index'))

@app.route("/create_meeting")
def create_meeting():
    return render_template('create_meeting.html') 

@app.route("/add_people", methods=['POST'])
def add_people():
    admin_email = request.form.get('email')
    daterange = request.form.get('daterange')
    begin_time = to_24(request.form.get('earliest'))
    end_time = to_24(request.form.get('latest'))
    daterange = daterange
    daterange_parts = daterange.split()
    begin_date = interpret_date(daterange_parts[0])
    end_date = interpret_date(daterange_parts[2])
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
                     daterange_parts[0], daterange_parts[1], 
                     begin_date, end_date))
    duration = request.form.get('duration')
    # Give a meeting code to this meeting
    meeting_code = random.randint(100000,999999)
    meeting = meetings.find_one({'code': meeting_code})
    # Make sure the code is unique
    while not meeting is None:
        meeting_code = random.randint(100000,999999)
        meeting = meetings.find_one({'code': meeting_code})
    A = Available(begin_date, end_date, begin_time, end_time)
    flask.session['meeting_code'] = meeting_code
    user = [{'email': admin_email, 'responded': False, 'times': A.to_iso(), 'avail': A.available}]
    meetings.insert({'code': meeting_code,
                     'admin': admin_email,
                     'begin_date': begin_date,
                     'end_date': end_date,
                     'begin_time': begin_time,
                     'end_time': end_time,
                     'duration': duration,
                     'users': user})
    return render_template('add_people.html')


@app.route("/_add_person")
def add_person():
    email = flask.request.args.get("email", type=str)
    code = flask.session['meeting_code']
    meeting = meetings.find_one({'code': code})
    users = meeting['users']
    if not email in users:
        A = Available(to_arrow(meeting['begin_date']), to_arrow(meeting['end_date']),
                  meeting['begin_time'], meeting['end_time'])
        users.append({'email': email,
                      'responded': False,
                      'times': A.to_iso(),
                      'avail': A.available})
        meetings.save(meeting)
        rslt = {"success": True}
    else:
        rslt = {"success": False}
    return flask.jsonify(result=rslt)


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


@app.route("/choose_events", methods=['GET', 'POST'])
def choose_events():
    ## For each calendar, print the events in date and time order
    app.logger.debug("Finding Events for each Calendar")

    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
        app.logger.debug("Redirecting to authorization")
        return flask.redirect(flask.url_for('oauth2callback'))

    service = get_gcal_service(credentials)

   
    calendars = flask.request.form.getlist('include')

    day_ranges = get_dateTime_list()

    time_min = day_ranges[0][0].floor('day')
    time_max = day_ranges[len(day_ranges)-1][1].ceil('day')

    events = []
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
                    event_start_time = to_arrow(list_events[i]['start']['date']).floor('day')
                    event_end_time = to_arrow(list_events[i]['start']['date']).ceil('day')
                else:
                    # normal event
                    event_start_time = to_arrow(list_events[i]['start']['dateTime'])
                    event_end_time = to_arrow(list_events[i]['end']['dateTime'])
                for date_range in day_ranges:
                    # Check if any part of an event overlaps
                    # Note: date/time range is not inclusive (using strict inequalities)
                    if date_range[0] < event_start_time < date_range[1] or \
                       date_range[0] < event_end_time < date_range[1] or \
                       (date_range[0] >= event_start_time and date_range[1] <= event_end_time):
                        
                        # make sure it's not being added twice
                        if list_events[i] in events:
                            continue
                        else:
                            events.append(list_events[i])

    # call a function that sorts the entire list of events by start date and time
    # and returns a printable string for the html page
    flask.g.events_list = events
    flask.g.events = sort_events(events)

    
    # render a new html page "show_events" that lists the events in order
    # I did this instead of rendering on the index page. I thought it was cleaner
    return render_template('choose_events.html')


@app.route("/show_available", methods=['POST'])
def show_available():
    """
    Shows times the user is available within the given date time range
    """
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
        app.logger.debug("Redirecting to authorization")
        return flask.redirect(flask.url_for('oauth2callback'))

    service = get_gcal_service(credentials)

    events = flask.request.form.getlist('events')
    
    flask.g.available = []
    meeting = meetings.find_one({'code': flask.session['meeting_code']})

    ignore_events = flask.request.form.getlist('ignore')
    
    i = find_user_index(meeting, flask.session['login_email'])
    if meeting['users'][i]['responded'] == True:
        A = Available(to_arrow(meeting['begin_date']), to_arrow(meeting['end_date']),
                      meeting['begin_time'], meeting['end_time'])
        meeting['users'][i]['times'] = A.to_iso()
        meeting['users'][i]['avail'] = A.available
        meeting['users'][i]['responded'] = False

    for event in events:
        event = eval(event)
        if 'date' in event['start']:
            # all day event
            event_start_time = to_arrow(event['start']['date']).floor('day')
            event_end_time = to_arrow(event['start']['date']).ceil('day')
        else:
            # normal event
            event_start_time = to_arrow(event['start']['dateTime'])
            event_end_time = to_arrow(event['end']['dateTime'])
 
        if not event['id'] in ignore_events:
            for j in range(len(meeting['users'][i]['times'])):
                if event_start_time <= to_arrow(meeting['users'][i]['times'][j]) < event_end_time:
                    meeting['users'][i]['avail'][j] = False
    meeting['users'][i]['responded'] = True
    meetings.save(meeting)
    flask.g.available = find_availability(meeting, flask.session['login_email'])
    return flask.redirect(flask.url_for('login'))

def to_arrow(time):
    return arrow.get(time).replace(tzinfo='US/Pacific')


def find_user_index(meeting, email):
    i=0
    while meeting['users'][i]['email'] != email:
        if i == len(meeting['users'])-1:
            return -1
        else:
            i+=1
    return i
 
def meeting_availability(meeting):
    A = Available(to_arrow(meeting['begin_date']), to_arrow(meeting['end_date']),
                  meeting['begin_time'], meeting['end_time'])
    printable_A = []
    not_responded = []
    duration = int(meeting['duration'])
    for i in range(len(meeting['users'])):
        if meeting['users'][i]['responded']:
            for j in range(len(A.time)):
                if not meeting['users'][i]['avail'][j]:
                    A.available[j] = False
        else:
            not_responded.append(meeting['users'][i]['email'])
    A.fixup(duration)
    i = 0
    started = False
    while i < len(A.time):
        if i == len(A.time)-1:
            if started:
                end_range = A.time[i]
                started = False
                printable_A.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        else:
            if not started:
                if A.time[i].shift(minutes=+15) == A.time[i+1] and A.available[i]:
                    start_range = A.time[i]
                    started = True
            else:
                if not A.time[i].shift(minutes=+15) == A.time[i+1] or not A.available[i]:
                    end_range = A.time[i]
                    started = False
                    printable_A.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        i+=1
    return [printable_A, not_responded]



def find_availability(meeting, email):
    i = find_user_index(meeting, email)
    availability = []
    j = 0
    started = False
    while j < len(meeting['users'][i]['times']):
        if j == len(meeting['users'][i]['times'])-1:
            if started:
                end_range = to_arrow(meeting['users'][i]['times'][j])
                started = False
                availability.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        else:
            if not started:
                if to_arrow(meeting['users'][i]['times'][j]).shift(minutes=+15) == to_arrow(meeting['users'][i]['times'][j+1]) and meeting['users'][i]['avail'][j]:
                    start_range = to_arrow(meeting['users'][i]['times'][j])
                    started = True
            else:
                if not to_arrow(meeting['users'][i]['times'][j]).shift(minutes=+15) == to_arrow(meeting['users'][i]['times'][j+1]) or not meeting['users'][i]['avail'][j]:
                    end_range = to_arrow(meeting['users'][i]['times'][j])
                    started = False
                    availability.append([start_range.format("MM-DD: h:mma"), end_range.format("MM-DD: h:mma")])
        j+=1
    return availability


def get_dateTime_list():
    """
    Returns a list of tuples that are start and end times for
    each acceptable chunk in the date range
    """
    code = flask.session['meeting_code']
    meeting = meetings.find_one({'code': code})
    b_hour, b_minute, e_hour, e_minute = get_flask_times(meeting)
    start_day = to_arrow(meeting['begin_date'])
    end_day = to_arrow(meeting['end_date']).ceil('day')
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

def get_flask_times(meeting):
    """
    Returns the integer versions of the time session objects as hour and minute
    """
    b_hour = int(meeting['begin_time'][:2])
    b_minute = int(meeting['begin_time'][-2:])
    e_hour = int(meeting['end_time'][:2])
    e_minute = int(meeting['end_time'][-2:])
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


def sort_events(events):
    """
    Sort events using a priority queue
    """
    H = []
    for event in events:
        if 'date' in event['start']:
            E = Event(to_arrow(event['start']['date']).floor('day'),
                 to_arrow(event['start']['date']).ceil('day'),
                 event['summary'], event['id'])
        else:
            E = Event(to_arrow(event['start']['dateTime']),
                 to_arrow(event['end']['dateTime']),
                 event['summary'], event['id'])
        heapq.heappush(H, E)
    events = []
    while H:
        events.append(heapq.heappop(H))
    return events

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
    return flask.redirect(flask.url_for('login'))

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

def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    return flask.redirect(flask.url_for("add_people"))




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
        as_arrow = to_arrow(text, time_formats).replace(tzinfo=tz.tzlocal())
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
    as_arrow = to_arrow(isotext)
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
    calendar_list = service.calendarList().list(showHidden=True).execute()["items"]
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
        normal = to_arrow( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = to_arrow( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    
