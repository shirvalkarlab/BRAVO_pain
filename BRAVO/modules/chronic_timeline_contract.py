"""Display contract for native chronic samples, without extrapolating the final interval."""


def chronic_timeline_activity(activity):
    times = activity["Time"]
    durations = [later - earlier for earlier, later in zip(times, times[1:])]
    if len(times):
        durations.append(None)  # There is no observed next timestamp for the final sample.
    return {
        "AnalysisType": "CustomizedTimelineData",
        "Time": times,
        "Duration": durations,
        "ChannelNames": activity["ChannelNames"],
        "ChannelUnits": activity["ChannelUnits"],
        "Data": activity["Data"],
    }
