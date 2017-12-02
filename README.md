*Program 10* 

Authors: M Young and P Hunter

Final iteration of the CIS 322 final project

What it does:
 - Allows a user (with a valid gmail account) to create a meeting with a unique 6-digit ID
 - Admin Functions:
    - Allows for the addition of attendees using gmail addresses only.
    - Allows a date range, time range for each day, and meeting duration (drop-down list).
    - Admin must set their available times, however, these can be changed later.
       - Automatically taken from google calendar, however user gets to choose calendars to include
         and events to ignore.
    - Admin is given their unique meeting ID to send to the attendees.
    - Admin can see who has not yet responded, and what the current status is.
    - Admin can delete a meeting (no warning, cannot be undone).
 - Non-Admin User Functions:
    - Can login to a meeting using their gmail address and unique code provided by meeting creator.
    - Can set available times specific to that meeting.
       - Taken from google calendar data.

Oddities: 
  -  If the first specified time is greater than the second time then assumes the user means
     for the time to extend into the next day.
     Example:
        Date Range: 1/1/2017 to 1/3/2017
        Time Range: 11:00 PM to 1:00 AM
        The application will produce all busy events in the given ranges:
            1/1/2017 11:00 PM to 1/2/2017 1:00 AM
            1/2/2017 11:00 PM to 1/3/2017 1:00 AM
            1/3/2017 11:00 PM to 1/4/2017 1:00 AM  <-- Bleeds over into the next day


Inclusions for V2:
 - Allow a user to create an account for access to all meetings attached to gmail address.
 - Allow for email addresses other than gmail.
 - Recall a deleted meeting.
 - Lookup a meeting by email address.
 - Allow users to set availability, then edit for specific meetings.
    - This sounds easy, but could be scheduling a meeting for a week from now, two weeks from now,
      three months from now, and six months from now, and don't want to have to sift through all that
      google calendar data.
 - Allow admins to edit meeting details and remove people from a meeting.
 - Give times when all but one person can meet, or maximum number of people (17 out of 20 for example).
 - Allow the admin to pick a time for the meeting and send an email to attendees, or even add the
   meeting directly to their calendars.
 - Add a logout button and clean up the cookie issues.
 - Add timezones other than Pacific
 - General clean-up.
 - General security improvements.
 - General code clean-up and logical improvements.


Known Issues:
 - There is an issue with cookies. They must be cleared when two people are scheduling from the same
   computer, the server does not do this automatically.
 - Because there is no logout the google authentication may persist even upon attempting to change
   gmail accounts.
 - There is absolutely no support for any timezone other than US/Pacific, all times are converted
   to this timezone (I'm sure incorrectly).
