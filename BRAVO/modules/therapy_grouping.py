"""Group therapy display rows by observed keys, preserving the legacy output order."""

THERAPY_TYPES = ("Pre-visit Therapy", "Post-visit Therapy", "Past Therapy")


def group_therapy_rows(rows):
    """Equivalent observed groups without scanning the source/date/group Cartesian product.

    Rows inside a group retain input order, exactly as the old stable sort on their
    identical Date values. Output order remains SourceId, Date, GroupId, then the
    explicit therapy-type order. Only the two settings lists are combined.
    """
    groups = {}
    for row in rows:
        if row["Type"] not in THERAPY_TYPES or row["Date"] != row["Date"]:
            # NaN dates did not match any old equality-filtered subset either.
            continue
        key = (row["SourceId"], row["Date"], row["GroupId"], THERAPY_TYPES.index(row["Type"]))
        if key not in groups:
            groups[key] = {**row, "StimulationSettings": list(row["StimulationSettings"]),
                           "AdaptiveSettings": list(row["AdaptiveSettings"])}
        else:
            groups[key]["StimulationSettings"].extend(row["StimulationSettings"])
            groups[key]["AdaptiveSettings"].extend(row["AdaptiveSettings"])
    return [groups[key] for key in sorted(groups)]
