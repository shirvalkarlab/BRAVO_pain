// UI affordances only. The server independently enforces the read-only account policy.
export const isReadOnlyUser = user => user?.ReadOnly === true;

export function viewerRouteAllowed(path = "") {
  return !/^\/(?:study-management|form-manager|survey|analysis-builder)(?:\/|$)/.test(path);
}

export function accountScope(user) {
  return JSON.stringify([user?.Email || null, user?.InstituteId || null,
    user?.StudyId || null, isReadOnlyUser(user)]);
}
