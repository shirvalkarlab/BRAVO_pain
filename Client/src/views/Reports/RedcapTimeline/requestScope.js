/** Scope in-flight read requests to the signed-in account, study and server.
 * This stores no results and does not replace the shared analysis result cache.
 */
import {SessionController} from 'database/session-control';
const users = new WeakMap();
let nextUser = 0;
const stable = value => {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]));
  return value;
};
export function cacheScope() {
  const user = SessionController.getUser();
  if (!user || typeof user !== 'object' || !Object.keys(user).length) return null;
  if (!users.has(user)) users.set(user, ++nextUser);
  const study = Object.fromEntries(Object.entries(SessionController.getSession() || {}).filter(([key]) => /study|permission|access/i.test(key)));
  return JSON.stringify(stable({account:user, generation:users.get(user), study, server:SessionController.getServer()}));
}
