/**
 * The participant's de-identified study code for the line under each page title ("RCS08 · pain
 * score Left Leg VAS", SPEC.md section 4 rule 1; the taste audit's E3, 2026-09-26).
 *
 * The code is read from the participant record the platform already serves
 * (`/api/queryParticipantInformation`, its `Name`), the same field the Stim Optimizer's sheet
 * export names a visit sheet by. It is printed ONLY when it has the shape of a study code: letters
 * and digits together, no spaces, at most 16 characters, and never the participant's long id. A
 * record whose name is a person's name, or a de-identified account's copy of the id, prints
 * nothing, and the line then names the pain score alone. Nothing is invented.
 */
import { useEffect, useState } from "react";

import { SessionController } from "database/session-control";

const CODE_SHAPE = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]{2,16}$/;
const LONG_ID = /^[0-9a-f]{32}$/i;

/** The study code from a participant record's name, or null when it does not look like one. */
export function studyCode(name, participantUid = null) {
  if (name == null) return null;
  const s = String(name).trim();
  if (!CODE_SHAPE.test(s) || LONG_ID.test(s)) return null;
  if (participantUid && s.toLowerCase() === String(participantUid).toLowerCase()) return null;
  return s;
}

const known = new Map();   // participant id -> study code or null, for this browser session

/** The study code for one participant, fetched once per session; null until (or unless) known. */
export function useStudyCode(participantUid) {
  const [code, setCode] = useState(() => (participantUid ? known.get(participantUid) || null : null));
  useEffect(() => {
    if (!participantUid) { setCode(null); return undefined; }
    if (known.has(participantUid)) { setCode(known.get(participantUid)); return undefined; }
    let cancelled = false;
    let pending;
    try {
      pending = SessionController.query("/api/queryParticipantInformation",
        { ParticipantId: participantUid });
    } catch (e) {
      pending = null;
    }
    Promise.resolve(pending)
      .then((response) => {
        const c = studyCode(response && response.data && response.data.Name, participantUid);
        known.set(participantUid, c);
        if (!cancelled) setCode(c);
      })
      .catch(() => { /* the line then names the pain score alone */ });
    return () => { cancelled = true; };
  }, [participantUid]);
  return code;
}
