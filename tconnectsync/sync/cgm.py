import json
import arrow
import logging

from ..parser.tconnect import TConnectEntry

logger = logging.getLogger(__name__)

def process_cgm_events(readingData):
    data = []
    for r in readingData:
        data.append(TConnectEntry.parse_reading_entry(r))
    
    return data

"""
Given reading data and a time, finds the BG reading event which would have
been the current one at that time. e.g., it looks before the given time,
not after.
This is a heuristic for checking whether the BG component of a bolus was
manually entered or inferred based on the pump's CGM.
"""
def find_event_at(cgmEvents, find_time):
    find_t = arrow.get(find_time)
    events = list(map(lambda x: (arrow.get(x["time"]), x), cgmEvents))
    events.sort()

    closestReading = None
    for t, r in events:
        if t > find_t:
            break
        closestReading = r
        
    
    return closestReading
    
