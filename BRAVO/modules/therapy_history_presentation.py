"""Opt-in response projection for the native therapy page; source/export stays intact."""


def therapy_history_response(history, compact=False):
    if compact is not True:
        return history
    result = dict(history)
    result["TherapyModification"] = [
        {**device, "History": [
            {key: value for key, value in row.items() if key != "Therapy"}
            for row in device["History"]
        ]}
        for device in history["TherapyModification"]
    ]
    result["TherapyTimeline"] = [
        {key: value for key, value in row.items() if key != "Therapies"}
        for row in history["TherapyTimeline"]
    ]
    return result
