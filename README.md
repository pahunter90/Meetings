Program 8

Authors: M Young and P Hunter

Second iteration of the CIS 322 final project

Uses: Lists all available time in given day and time ranges using events from Google calendars.
Note: The specified time range is for each day.
      If the user wants all events in one day then use 12:00 AM to 12:00 AM
      which will pick up all events on all days in the given range, so long as said
      events are marked as busy times.

Date Range: From MM/DD/YYYY to MM/DD/YYYY
Time Range: From HH:MM AA to HH:MM PP
            15 minute increments only: I.e.: 11:45 PM allowed, 11:56 PM not allowed.
            Must specify AM or PM

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
