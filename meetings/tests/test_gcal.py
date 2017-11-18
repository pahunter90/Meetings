"""
Nosetests for gcal usage
"""

from available import Available
from event import Event
import arrow

#GLOBAL TIME VARIABLES TO USE THROUGHOUT
CURRENT_TIME = arrow.now()
NEXT_DAY = CURRENT_TIME.shift(days=+1)
DAY_AFTER = CURRENT_TIME.shift(days=+2)

def test_event_creation():
    E = Event(CURRENT_TIME, NEXT_DAY, "Fake Event", "123456")
    assert E.start == CURRENT_TIME
    assert E.end == NEXT_DAY
    assert E.summary == "Fake Event"
    assert E.id == "123456"

def test_event_comparisons():
    E = Event(CURRENT_TIME, NEXT_DAY, "Fake Event", "123456")
    V = Event(NEXT_DAY, DAY_AFTER, "Another Fakie", "234567")
    N = Event(CURRENT_TIME, DAY_AFTER, "Faked Thrice", "345678")
    T = Event(CURRENT_TIME, NEXT_DAY, "Fake Event 2", "123457")
    assert E == T
    assert E < V
    assert E < N
    assert E != N
    assert T == T
    assert V > N
    assert V >= N
    assert E <= N

def test_avail_creation():
    start = "2017-01-01"
    end = "2017-01-07"
    times = [12,00,21,45]
    A = Available(start, end, times)
    assert len(A.time) == len(A.available)
    for i in range(len(A.available)):
        assert A.available[i] == True
    assert arrow.get('2017-01-01 12:00').replace(tzinfo='US/Pacific') in A.time
    assert arrow.get('2017-01-04 15:30').replace(tzinfo='US/Pacific') in A.time
    assert arrow.get('2017-01-07 21:45').replace(tzinfo='US/Pacific') in A.time
    assert arrow.get('2017-01-07 11:45').replace(tzinfo='US/Pacific') not in A.time
    assert arrow.get('2017-01-07 22:00').replace(tzinfo='US/Pacific') not in A.time
