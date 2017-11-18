import arrow

class Event:
    def __init__(self, start_date_time, end_date_time, summary, event_id):
        """
        Create and Event object using the start_date_time, end_date_time, summary, event_id,
        and create a printable string for the event (dt_string - dt stands for datetime)
        """
        self.start = start_date_time
        self.end = end_date_time
        self.summary = summary
        self.id = event_id
        if start_date_time.date() == end_date_time.date():
            self.dt_string = start_date_time.format("MM-DD: hh:mma") + " to " + end_date_time.format("hh:mma")
        else:
            self.dt_string = start_date_time.format("MM-DD: hh:mma") + " to " + end_date_time.format("MM:DD: hh:mma")

    def __lt__(self, other):
        return self.start < other.start

    def __eq__(self, other):
        return self.start == other.start

    def __gt__(self, other):
        return other.__lt__(self)

    def __le__(self, other):
        return self.__lt__(other) or self.__eq__(other)

    def __ge__(self, other):
        return other.__le__(self)

    def __ne__(self, other):
        return not self.__eq__(other)            
