import arrow
import logging

from tconnectsync.sync.cgm import find_event_at

from ..parser.tconnect import TConnectEntry
from ..secret import SKIP_NS_LAST_UPLOADED_CHECK

logger = logging.getLogger(__name__)

"""
Given bolus data input from the therapy timeline CSV, converts it into a digestable format.
"""
def process_bolus_events(bolusdata, cgmEvents=None):
    bolusEvents = []

    for b in bolusdata:
        parsed = TConnectEntry.parse_bolus_entry(b)
        if parsed["completion"] != "Completed":
            if parsed["insulin"] and float(parsed["insulin"]) > 0:
                # Count non-completed bolus if any insulin was delivered (vs. the amount of insulin requested)
                parsed["description"] += " (%s: requested %s units)" % (parsed["completion"], parsed["requested_insulin"])
            else:
                logger.warning("Skipping non-completed bolus data (was a bolus in progress?): %s parsed: %s" % (b, parsed))
                continue

        if parsed["bg"] and cgmEvents:
            requested_at = parsed["request_time"] if not parsed["extended_bolus"] else parsed["bolex_start_time"]
            parsed["bg_type"] = guess_bolus_bg_type(parsed["bg"], requested_at, cgmEvents)

        bolusEvents.append(parsed)

    bolusEvents.sort(key=lambda event: arrow.get(event["request_time"] if not event["extended_bolus"] else event["bolex_start_time"]))

    return bolusEvents

"""
Determine whether the given BG specified in the bolus is identical to the
most recent CGM reading at that time. If it is, return SENSOR.
Otherwise, return FINGER.
"""
def guess_bolus_bg_type(bg, created_at, cgmEvents):
    if not cgmEvents:
        return "finger"

    event = find_event_at(cgmEvents, created_at)
    if event and str(event["bg"]) == str(bg):
        return "sensor"
    
    return "finger"

