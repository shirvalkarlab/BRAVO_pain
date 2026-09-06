// Reviewed UI names only. Tablet target/hemisphere identifiers remain unchanged
// in records, channel selections, API requests and scientific calculations.
export const RCS08_PARTICIPANT_ID = "81b245ec31594d9894f1dfc9438b6348";

export function isRCS08Participant(participant) {
  if (typeof participant === "string") {
    return participant === RCS08_PARTICIPANT_ID || participant.trim().toUpperCase() === "RCS08";
  }
  if (!participant || typeof participant !== "object") return false;
  return [participant.Id, participant.id, participant.uid, participant.ParticipantId,
    participant.Name, participant.name].some(value => typeof value === "string" && isRCS08Participant(value));
}

export function displayTarget(participant, hemisphere, fallback = hemisphere) {
  if (!isRCS08Participant(participant)) return fallback;
  const side = String(hemisphere || "").replace(/^HemisphereLocationDef\./i, "");
  if (/^(?:left(?:hemisphere)?|l)(?:\b|_)/i.test(side)) return "L GPe";
  if (/^(?:right(?:hemisphere)?|r)(?:\b|_)/i.test(side)) return "R MD Thal";
  return fallback;
}

export function displayTargetText(participant, text) {
  if (!isRCS08Participant(participant) || typeof text !== "string") return text;
  return text
    .replace(/\b(?:Left(?:Hemisphere)?|L)\s+(?:GPi|GPe)\b/gi, "L GPe")
    .replace(/\b(?:Right(?:Hemisphere)?|R)\s+(?:MD\s+Thal(?:amus)?|Thal(?:amus)?|VIM)\b/gi, "R MD Thal")
    .replace(/\bLeft\s*Hemisphere\b/gi, "L GPe")
    .replace(/\bRight\s*Hemisphere\b/gi, "R MD Thal")
    .replace(/\b(?:Left|L) (?=\d)/gi, "L GPe ")
    .replace(/\b(?:Right|R) (?=\d)/gi, "R MD Thal ");
}

// Legacy plot managers are not React components. Resolve only the participant
// segment of an actual report/participant route; never use sticky session state.
export function routeParticipant(pathname = typeof window === "undefined" ? "" : window.location.pathname) {
  return String(pathname).split("/").filter(Boolean).find(part => part === RCS08_PARTICIPANT_ID) || null;
}

export function currentTarget(hemisphere, fallback = hemisphere) {
  return displayTarget(routeParticipant(), hemisphere, fallback);
}

export function currentTargetText(text) {
  return displayTargetText(routeParticipant(), text);
}
