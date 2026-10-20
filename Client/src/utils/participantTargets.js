// Public builds preserve recorded labels. Participant identifiers never imply anatomy.
// Private deployments may provide reviewed display context through their own configuration.
export function displayTarget(participant, hemisphere, fallback = hemisphere) {
  return fallback;
}

export function displayTargetText(participant, text) {
  return text;
}

// Kept for legacy callers; a URL cannot supply reviewed anatomical evidence.
export function routeParticipant() {
  return null;
}

export function currentTarget(hemisphere, fallback = hemisphere) {
  return fallback;
}

export function currentTargetText(text) {
  return text;
}
