/**
 * The safe current ceiling per side, READ from the server's response and never typed here (SPEC.md
 * section 4, rule 1: "read from the server and never typed in"). The page head's ceiling line and
 * the current map's dashed ceiling lines both read it through this one function.
 *
 * Where the value is carried, in order: the closed-loop checks' current-limit check
 * (`gate.conditions[].evidence.ceiling_by_side`), the home schedule (`ceiling_left_mA` /
 * `ceiling_right_mA`), the titration plan's two sides (`sides[side].ceiling_mA`) and the
 * readiness screen (`closed_loop.safe_ceiling_mA_by_side`). A side found nowhere is null, and the
 * line then says it was not received rather than printing a number.
 */
import { num } from "./stimFormat";

export function ceilingFromPlan(plan) {
  const out = { leftMa: null, rightMa: null };
  const conds = (((plan && plan.gate) || {}).conditions) || [];
  conds.forEach((c) => {
    const by = c && c.evidence && c.evidence.ceiling_by_side;
    if (!by) return;
    if (out.leftMa === null && by.Left) out.leftMa = num(by.Left.ceiling_mA);
    if (out.rightMa === null && by.Right) out.rightMa = num(by.Right.ceiling_mA);
  });
  return out;
}

export function ceilingFromResponse(data, plan) {
  const out = ceilingFromPlan(plan);
  const d = data || {};
  const fill = (l, r) => {
    if (out.leftMa === null) out.leftMa = num(l);
    if (out.rightMa === null) out.rightMa = num(r);
  };
  const sch = d.current_map_schedule || {};
  fill(sch.ceiling_left_mA, sch.ceiling_right_mA);
  const sides = ((d.titration_plan || {}).sides) || {};
  fill(sides.Left && sides.Left.ceiling_mA, sides.Right && sides.Right.ceiling_mA);
  const cl = ((d.closed_loop || {}).safe_ceiling_mA_by_side) || {};
  fill(cl.Left, cl.Right);
  return out;
}
