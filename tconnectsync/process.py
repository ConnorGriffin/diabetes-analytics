import logging
import datetime
import arrow
import time
import os
import json 

from .util import timeago
from .api.common import ApiException
from .sync.basal import (
    process_ciq_basal_events,
    add_csv_basal_events
)
from .sync.bolus import (
    process_bolus_events
)
from .sync.iob import (
    process_iob_events
)
from .sync.cgm import (
    process_cgm_events
)
from .sync.pump_events import (
    process_ciq_activity_events,
    process_basalsuspension_events
)
from .parser.tconnect import TConnectEntry
from .features import BASAL, BOLUS, IOB, BOLUS_BG, CGM, DEFAULT_FEATURES, PUMP_EVENTS

logger = logging.getLogger(__name__)

"""
Given a TConnectApi object and start/end range, performs a single
cycle of synchronizing data within the time range.
If pretend is true, then doesn't actually write data to Nightscout.
"""
def process_time_range(tconnect, time_start, time_end, pretend, features=DEFAULT_FEATURES):
    logger.info("Downloading t:connect ControlIQ data")
    try:
        ciqTherapyTimelineData = tconnect.controliq.therapy_timeline(time_start, time_end)
    except ApiException as e:
        # The ControlIQ API returns a 404 if the user did not have a ControlIQ enabled
        # device in the time range which is queried. Since it launched in early 2020,
        # ignore 404's before February.
        if e.status_code == 404 and time_start.date() < datetime.date(2020, 2, 1):
            logger.warning("Ignoring HTTP 404 for ControlIQ API request before Feb 2020")
            ciqTherapyTimelineData = None
        else:
            raise e

    logger.info("Downloading t:connect CSV data")
    csvdata = tconnect.ws2.therapy_timeline_csv(time_start, time_end)

    readingData = csvdata["readingData"]
    iobData = csvdata["iobData"]
    csvBasalData = csvdata["basalData"]
    bolusData = csvdata["bolusData"]

    dataExport = {}

    if readingData and len(readingData) > 0:
        lastReading = readingData[-1]['EventDateTime'] if 'EventDateTime' in readingData[-1] else 0
        lastReading = TConnectEntry._datetime_parse(lastReading)
        logger.debug(readingData[-1])
        logger.info("Last CGM reading from t:connect: %s (%s)" % (lastReading, timeago(lastReading)))
    else:
        logger.warning("No last CGM reading is able to be determined")

    if BASAL in features:
        basalEvents = process_ciq_basal_events(ciqTherapyTimelineData)
        if csvBasalData:
            logger.debug("CSV basal data found: processing it")
            add_csv_basal_events(basalEvents, csvBasalData)
        else:
            logger.debug("No CSV basal data found")
        dataExport['basalEvents'] = basalEvents

    if BOLUS in features:
        bolusEvents = process_bolus_events(bolusData)
        dataExport['bolusEvents'] = bolusEvents

    if IOB in features:
        iobEvents = process_iob_events(iobData)
        dataExport['iobEvents'] = iobEvents

    if PUMP_EVENTS in features:
        pumpEvents = process_ciq_activity_events(ciqTherapyTimelineData)
        logger.debug("CIQ activity events: %s" % pumpEvents)

        ws2BasalSuspension = tconnect.ws2.basalsuspension(time_start, time_end)

        bsPumpEvents = process_basalsuspension_events(ws2BasalSuspension)
        logger.debug("basalsuspension events: %s" % bsPumpEvents)

        pumpEvents += bsPumpEvents
        dataExport['pumpEvents'] = pumpEvents
    

    with open('tconnect-data/basalEvents.json', 'w') as f:
        json.dump(dataExport['basalEvents'], f)

    with open('tconnect-data/bolusEvents.json', 'w') as f:
        json.dump(dataExport['bolusEvents'], f)

    with open('tconnect-data/iobEvents.json', 'w') as f:
        json.dump(dataExport['iobEvents'], f)

    with open('tconnect-data/pumpEvents.json', 'w') as f:
        json.dump(dataExport['pumpEvents'], f)

    with open('tconnect-data/cgmData.json', 'w') as f:
        json.dump(readingData, f)