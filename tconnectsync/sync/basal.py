import arrow
import logging

from ..parser.tconnect import TConnectEntry
from ..secret import SKIP_NS_LAST_UPLOADED_CHECK

logger = logging.getLogger(__name__)

"""
Merges together input from the therapy timeline API
into a digestable format of basal data.
"""
def process_ciq_basal_events(data):
    if data is None:
        return []

    suspensionEvents = {}
    for s in data["suspensionDeliveryEvents"]:
        entry = TConnectEntry.parse_suspension_entry(s)
        suspensionEvents[entry["time"]] = entry

    basalEvents = []
    for b in data["basal"]["tempDeliveryEvents"]:
        basalEvents.append(TConnectEntry.parse_ciq_basal_entry(b, delivery_type="tempDelivery"))

    for b in data["basal"]["algorithmDeliveryEvents"]:
        basalEvents.append(TConnectEntry.parse_ciq_basal_entry(b, delivery_type="algorithmDelivery"))

    for b in data["basal"]["profileDeliveryEvents"]:
        basalEvents.append(TConnectEntry.parse_ciq_basal_entry(b, delivery_type="profileDelivery"))


    # Suspensions with suspendReason 'control-iq' will match a basal event found above.
    for i in basalEvents:
        if i["time"] in suspensionEvents:
            i["delivery_type"] += " (" + suspensionEvents[i["time"]]["suspendReason"] + " suspension)"

            del suspensionEvents[i["time"]]
    
    # Suspensions with suspendReason 'manual' do not have an associated basal event,
    # and require extra processing.

    basalEvents.sort(key=lambda x: arrow.get(x["time"]))

    unprocessedSuspensions = list(suspensionEvents.values())
    unprocessedSuspensions.sort(key=lambda x: arrow.get(x["time"]))

    # For the remaining suspensions which did not match with an existing basal event,
    # add a new event manually. This means we need to calculate the duration of the
    # suspension.
    newEvents = []
    for i in range(len(basalEvents)):
        if len(unprocessedSuspensions) == 0:
            break

        existingTime = arrow.get(basalEvents[i]["time"])
        unprocessedTime = arrow.get(unprocessedSuspensions[0]["time"])
        
        # If we've found an event which occurs after the suspension, then the
        # difference in their timestamps is the duration of the suspension.
        if i > 0 and existingTime > unprocessedTime:
            suspension = unprocessedSuspensions.pop(0)

            # TConnect's internal duration object tracks the duration in seconds
            seconds = (existingTime - unprocessedTime).seconds

            newEvent = TConnectEntry.manual_suspension_to_basal_entry(suspension, seconds)
            logger.debug("Adding basal event for unprocessed suspension: %s" % newEvent)
            newEvents.append(newEvent)

    # Any remaining suspensions which have not been processed have not ended,
    # which means we do not know their duration; so we will skip them (for now)

    # Add any new events and re-sort
    if newEvents:
        basalEvents += newEvents
        basalEvents.sort(key=lambda x: arrow.get(x["time"]))


    return basalEvents

"""
Processes basal data input from the therapy timeline CSV (which only
exists for pre Control-IQ data) into a digestable format.
"""
def add_csv_basal_events(basalEvents, data):
    last_entry = {}
    for row in data:
        entry = TConnectEntry.parse_csv_basal_entry(row)
        if last_entry:
            diff_mins = (arrow.get(entry["time"]) - arrow.get(last_entry["time"])).seconds // 60
            entry["duration_mins"] = diff_mins

        basalEvents.append(entry)
        last_entry = entry

    basalEvents.sort(key=lambda x: arrow.get(x["time"]))
    return basalEvents