/**
 * Page review 2026-10-02 (item 4.7): every page logged "WebSocket ... /socket/notification failed".
 * The server has no such endpoint (its ASGI app serves HTTP only), and a failed WebSocket is logged
 * by the browser itself, which page code cannot silence. So the socket is not opened while the
 * endpoint is absent; one flag turns it back on.
 */
import { NOTIFICATION_SOCKET_ENABLED, openNotificationSocket } from "./notificationSocket";

describe("the notification socket", () => {
  it("is off while the server has no endpoint, and opens nothing", () => {
    const spy = jest.fn();
    global.WebSocket = spy;
    expect(NOTIFICATION_SOCKET_ENABLED).toBe(false);
    const getUrl = jest.fn(() => "ws://host/socket/notification");
    expect(openNotificationSocket(getUrl)).toBeNull();
    expect(getUrl).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
  });
});
