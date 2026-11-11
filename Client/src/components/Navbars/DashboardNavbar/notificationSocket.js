/**
 * The live processing-queue notification socket. The server has no /socket/notification endpoint
 * (its ASGI app serves HTTP only, no Channels consumer), and a WebSocket that fails is logged by the
 * browser itself, so every page load printed "WebSocket ... failed" (page review 2026-10-02, 4.7).
 * It is therefore not opened while the endpoint is absent; set the flag when a backend exists.
 */
export const NOTIFICATION_SOCKET_ENABLED = false;

/** `getUrl` builds the address only when the socket is on, inside the try, as the navbar did. */
export function openNotificationSocket(getUrl) {
  if (!NOTIFICATION_SOCKET_ENABLED) return null;
  try {
    return new WebSocket(getUrl());
  } catch (e) {
    return null;
  }
}
