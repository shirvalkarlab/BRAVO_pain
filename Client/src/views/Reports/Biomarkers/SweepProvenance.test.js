import '@testing-library/jest-dom';
import {render,screen,fireEvent} from '@testing-library/react';
import {wrap} from 'testUtils/render';
import {gridSourceWords,bandSelectionWords,CurrentScopeNotes,SourceGridDetails} from './SweepProvenance';

const draw=ui=>render(wrap(ui));
const current={current_scope:'median over candidate pieces before per-band artifact rejection; shared across window lengths',what:'Current accounted for descriptively.',n_reports_without_current:2};
const row={band_center_hz:12.5,pearson_r:0.24,integration_seconds_delivered:9,n_pain_reports:20,current_removed_check:current};
test('source provenance prioritizes the selected TD grid over inherited mixed metadata',()=>{
 expect(gridSourceWords({grid_source:'td_psd_where_no_td',choosing_grid:'td'})).toMatch(/^TD-only/);
 expect(gridSourceWords({grid_source:'td_psd_where_no_td'})).toMatch(/^Mixed grid/);
 expect(gridSourceWords({grid_source:'psd'})).toMatch(/cannot select a band/);
 expect(gridSourceWords({choosing_grid:'none',choosing_grid_reason:'No TD evidence'})).toBe('No TD evidence');
 expect(gridSourceWords({choosing_grid:'none'})).toMatch(/No grid/);
 expect(gridSourceWords(null)).toMatch(/not reported/);
 expect(gridSourceWords({grid_source:'unrecognized'})).toMatch(/not reported/);
});
test('current details report the actual approximation and missing-current subset without inventing coverage',()=>{
 const {rerender}=draw(<CurrentScopeNotes sweep={{best_correlation_rows:[row]}}/>);
 expect(screen.getByText(/Current is an approximation/)).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Current-adjustment details by band'}));
 expect(screen.getByText(/median over candidate pieces/)).toHaveTextContent('2 otherwise eligible reports lack current');
 rerender(wrap(<CurrentScopeNotes sweep={{best_correlation_rows:[{current_removed_check:{}}]}}/>));
 expect(screen.getByText(/Adjustment details not reported/)).toHaveTextContent('Missing-current count not reported');
 rerender(wrap(<CurrentScopeNotes sweep={null}/>));
 expect(screen.queryByTestId('current-scope-notes')).not.toBeInTheDocument();
 rerender(wrap(<CurrentScopeNotes sweep={{best_correlation_rows:[{}]}}/>));
 expect(screen.queryByTestId('current-scope-notes')).not.toBeInTheDocument();
});
test('source tables display distinct source statistics and own windows, never use mixed fallback or selection buttons',()=>{
 const {rerender}=draw(<SourceGridDetails sweep={{best_correlation_rows:[{...row,pearson_r:0.99}],by_source_grid:{td:{best_correlation_rows:[row],best_auc_rows:[{band_center_hz:12.5,auc:0.72,integration_seconds_delivered:18,n_pain_reports:16}]},psd:{best_correlation_rows:[{...row,pearson_r:-0.13,current_removed_check:undefined}],best_auc_rows:[]}}}}/>);
 fireEvent.click(screen.getByRole('button',{name:'TD-only and PSD-only results'}));
 expect(screen.getByTestId('source-grid-td')).toHaveTextContent('0.24');
 expect(screen.getByTestId('source-grid-td')).toHaveTextContent('0.72');
 expect(screen.getByTestId('source-grid-td')).toHaveTextContent('18');
 expect(screen.getByTestId('source-grid-psd')).toHaveTextContent('-0.13');
 expect(screen.queryByText('0.99')).not.toBeInTheDocument();
 expect(screen.queryByRole('radio')).not.toBeInTheDocument();
 rerender(wrap(<SourceGridDetails sweep={{by_source_grid:{td:{reason:'Too few TD reports'},psd:{best_auc_rows:[{auc:Infinity}]}}}}/>));
 expect(screen.getByTestId('source-grid-td')).toHaveTextContent('Too few TD reports');
 expect(screen.getByTestId('source-grid-psd')).toHaveTextContent('not reported');
 rerender(wrap(<SourceGridDetails sweep={{by_source_grid:{}}}/>));
 expect(screen.getAllByText('This source grid was not returned.')).toHaveLength(2);
 rerender(wrap(<SourceGridDetails sweep={null}/>));
 expect(screen.queryByTestId('source-grid-td')).not.toBeInTheDocument();
});

test('C5 labels preserve displayed source and separate chronic correlation from TD AUC', () => {
 const chronic = {frequencies: [{freq_hz: 12.5}]};
 expect(gridSourceWords({grid_source:'td_psd_where_no_td', chronic_band_choice: chronic})).toMatch(/^Mixed grid/);
 expect(bandSelectionWords({chronic_band_choice: chronic})).toContain('home chronic-log correlation where it covers the band; otherwise TD-only correlation');
 expect(bandSelectionWords({best_correlation_rows:[{choice_source:'chronic'}]})).toContain('AUC remains TD-only');
 expect(bandSelectionWords({best_correlation_rows:[{choice_source:'TD'}]})).toContain('PSD-only and mixed results are descriptive');
 expect(bandSelectionWords({})).toContain('does not report the chronic-log selection policy');
 expect(bandSelectionWords(null)).toContain('does not report');
 expect(bandSelectionWords({best_correlation_rows:[{}]})).toContain('does not report');
 expect(gridSourceWords({grid_source:'td',chronic_band_choice:{status:'read_failed'}})).toContain('Band selection is unavailable');
 expect(gridSourceWords({grid_source:'psd',chronic_band_choice:{status:'read_failed'}})).toContain('could not be read completely');
});
