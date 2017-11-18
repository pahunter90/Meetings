import arrow

class Available:
    def __init__(self, start_date, end_date, times):
        """
        Takes a starting date, ending date, 24hr start time, 24hr end time
        and returns an array with acceptable times in 15 minute increments
        with a parallel boolean array that initializes to true for all values
        """
        self.time = []
        self.available = []
        start_date_time = arrow.get(start_date).floor('day').replace(tzinfo='US/Pacific')
        end_date_time = arrow.get(start_date).floor('day').replace(tzinfo='US/Pacific')
        last_date_time = arrow.get(end_date).floor('day').replace(tzinfo='US/Pacific')
        start_hour = times[0]
        start_minute = times[1]
        end_hour = times[2]
        end_minute = times[3]
        start_date_time = start_date_time.replace(hour=start_hour, minute=start_minute)
        end_date_time = end_date_time.replace(hour=end_hour, minute=end_minute)
        last_date_time = last_date_time.replace(hour=end_hour, minute=end_minute)
        if start_date_time >= end_date_time:
            end_date_time = end_date_time.shift(days=+1)
            last_date_time = last_date_time.shift(days=+1)
        while end_date_time <= last_date_time:
            while start_date_time < end_date_time:
                if not start_date_time in self.time:
                    self.time.append(start_date_time)
                    self.available.append(True)
                start_date_time = start_date_time.shift(minutes=+15)
            start_date_time = start_date_time.replace(hour=start_hour, minute=start_minute)
            if not start_date_time == end_date_time:
                start_date_time = start_date_time.shift(days=+1)
            if not end_date_time in self.time:
                self.time.append(end_date_time)
                self.available.append(True)
            end_date_time = end_date_time.shift(days=+1)
