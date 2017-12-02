import arrow

class Available:
    def __init__(self, start_date, end_date, start_time, end_time):
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
        start_hour = int(start_time[0:2])
        start_minute = int(start_time[3:5])
        end_hour = int(end_time[0:2])
        end_minute = int(end_time[3:5])
        start_date_time = start_date_time.replace(hour=start_hour, minute=start_minute)
        end_date_time = end_date_time.replace(hour=end_hour, minute=end_minute)
        last_date_time = last_date_time.replace(hour=end_hour, minute=end_minute)
        wrap_around = False
        if start_date_time >= end_date_time:
            end_date_time = end_date_time.shift(days=+1)
            last_date_time = last_date_time.shift(days=+1)
            wrap_around = True
        while end_date_time <= last_date_time:
            while start_date_time < end_date_time:
                if not start_date_time in self.time:
                    self.time.append(start_date_time)
                    self.available.append(True)
                start_date_time = start_date_time.shift(minutes=+15)
            start_date_time = start_date_time.replace(hour=start_hour, minute=start_minute)
            if not wrap_around:
                start_date_time = start_date_time.shift(days=+1)
            if not end_date_time in self.time:
                self.time.append(end_date_time)
                self.available.append(True)
            end_date_time = end_date_time.shift(days=+1)

    def to_iso(self):
        times = []
        for time in self.time:
            times.append(time.isoformat())
        return times

    def fixup(self, duration):
        minimum = int(duration/15)
        print(minimum)
        start = 0
        end = 0
        for i in range(len(self.available)):
            if not self.available[i]:
                self.check_min(start, end, minimum)
                end = i+1 
                start = end
            else:
                if i == len(self.available) - 1:
                    end = i
                    self.check_min(start, end, minimum)
                elif not self.time[i].shift(minutes=+15) == self.time[i+1]:
                    end = i
                    self.check_min(start, end, minimum)
                    end = i + 1
                    start = end
                else:
                    end = i

    # Helper function for fixup
    def check_min(self, start, end, minimum):
        if end - start + 1 < minimum:
            while start <= end:
                self.available[start] = False
                start += 1
                    
