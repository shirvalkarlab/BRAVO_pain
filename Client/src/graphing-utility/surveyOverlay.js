// Both native score forms and legacy linked REDCap forms use page/question indices.
export function surveyOverlaySeries({form = [], records = []} = {}) {
  if (!Array.isArray(form) || !Array.isArray(records)) return [];
  return form.flatMap((page, pageIndex) => (page.questions || []).flatMap((question, questionIndex) => {
    if (!['score', 'redcapForm'].includes(question.type) || question.text === 'Time' || question.show === false) return [];
    const x = [], y = [];
    for (const record of records) {
      const value = record.Result?.[pageIndex]?.[questionIndex];
      if (!['number', 'string'].includes(typeof value) || String(value).trim() === '') continue;
      const score = Number(value);
      if (!Number.isFinite(score) || !Number.isFinite(record.Date)) continue;
      x.push(new Date(record.Date * 1000)); y.push(score);
    }
    return x.length ? [{key: `${pageIndex}:${questionIndex}`, name: question.text, x, y}] : [];
  }));
}

// Repeated toggles must not accumulate right axes or leave empty score axes behind.
export function clearSurveyOverlayAxes(fig) {
  fig.ax = fig.ax.filter(axis => {
    if (!axis.surveyOverlay) return true;
    delete fig.layout[axis.ylayout];
    return false;
  });
  if (fig.gca?.surveyOverlay) fig.gca = fig.ax[0];
}
