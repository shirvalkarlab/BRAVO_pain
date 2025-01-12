/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useState, useCallback, useEffect } from "react";
import { useResizeDetector } from 'react-resize-detector';

import MDBox from "components/MDBox";

import colormap from "colormap";
import { TwitterPicker, BlockPicker } from "react-color";

import { Autocomplete, Card, Menu, MenuItem, Dialog, DialogContent, Grid, IconButton, Popover, TextField, DialogActions } from "@mui/material";
import MDTypography from "components/MDTypography";
import RadioButtonGroup from "components/RadioButtonGroup";
import FormField from "components/MDInput/FormField";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { dictionary, dictionaryLookup } from "assets/translation";
import { usePlatformContext } from "context";

function RecordScoreTimeline({dataToRender, form, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [popup, setPopupState] = useState({item: ""});

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [activeScores, setActiveScores] = useState([]);
  const [availableScores, setAvailableScores] = useState([]);

  useEffect(() => {
    setFig(new PlotlyRenderManager(figureTitle, language));
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setYlabel("Score", {fontsize: 15});
    fig.setLegend({
      x: 0, y: -0.2,
      xanchor: 'left', yanchor: "top",
      orientation: "h", 
    })
      
    if (!fig.fresh) {
      refreshRender();
    }
  }, [fig]);

  useEffect(() => {
    let options = [];
    for (let page in form) {
      for (let i in form[page].questions) {
        if (form[page].questions[i].type == "score") {
          options.push({
            type: "score",
            label: form[page].questions[i].text,
            page: page,
            index: i,
            defaultActive: form[page].questions[i].activeView
          });
        } else if (form[page].questions[i].type == "cumulativeScore") {
          options.push({
            type: "cumulativeScore",
            label: form[page].questions[i].text,
            page: page,
            index: i,
            defaultActive: form[page].questions[i].activeView,
            list: form[page].questions[i].list.map((a) => {
              for (let b in form) {
                for (let c in form[b].questions) {
                  if (a == form[b].questions[c].text) {
                    return {
                      page: b, index: c
                    }
                  }
                }
              }
              return {};
            })
          });
        }
      }
    }
    setAvailableScores(options);
    setActiveScores(options.filter((a) => a.defaultActive))
  }, [form]);

  useEffect(() => {
    if (!fig) return;

    const colors = colormap({
      colormap: 'rainbow',
      nshades: activeScores.length < 10 ? 10 : activeScores.length,
      format: 'hex',
      alpha: 1,
    });

    let graphSeries = [];
    for (let i in activeScores) {

      if (activeScores[i].type == "score") {
        let xData = [], yData = [];
        for (let j in dataToRender) {
          xData.push(new Date(dataToRender[j].Date*1000));
          yData.push(dataToRender[j].Result[activeScores[i].page][activeScores[i].index])
        }
        graphSeries.push({
          type: "line", x: xData, y: yData, 
          options: {
            mode: "lines+markers",
            linewidth: 2,
            name: activeScores[i].label,
            color: colors[i],
            hovertemplate: `  ${activeScores[i].label}:  %{y:.2f}<extra></extra>`,
            showlegend: true
          }
        })
      } else if (activeScores[i].type == "cumulativeScore") {
        let xData = [], yData = [];
        for (let j in dataToRender) {
          xData.push(new Date(dataToRender[j].Date*1000));
          yData.push(activeScores[i].list.reduce((cumulativeScore, a) => {
            if (a.page) {
              return cumulativeScore + dataToRender[j].Result[a.page][a.index];
            }
            return cumulativeScore
          }, 0));
        }
        graphSeries.push({
          type: "line", x: xData, y: yData, 
          options: {
            mode: "lines+markers",
            linewidth: 2,
            name: activeScores[i].label,
            color: colors[i],
            hovertemplate: `  ${activeScores[i].label}:  %{y:.2f}<extra></extra>`,
            showlegend: true
          }
        })
      }

    }

    setRenderData(graphSeries);

  }, [dataToRender, activeScores])

  const refreshRender = () => {
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.plot(renderData[i].x, renderData[i].y, renderData[i].options);
      }
    }
    fig.render();
  }

  // Refresh Left Figure if Data Changed
  useEffect(() => {
    if (!fig) return;
    
    fig.traces = [];
    refreshRender();
  }, [fig, renderData]);

  const onResize = useCallback(() => {
    if (!fig) return;

    fig.refresh();
  }, [fig]);

  const {ref} = useResizeDetector({
    onResize: onResize,
    refreshMode: "debounce",
    refreshRate: 50,
    skipOnMount: false
  });

  return (
    <Grid>
      <Grid item xs={12}>
        <MDBox px={2} pb={2}>
          <Autocomplete
            multiple disableClearable
            value={activeScores}
            options={availableScores}
            onChange={(event, value) => {
              setActiveScores(value)
            }}
            isOptionEqualToValue={(option, value) => {
              return option.label === value.label;
            }}
            renderOption={(props, option) => <li {...props}>{option.label}</li>}
            getOptionLabel={(option) => {
              if (typeof option === 'string') {
                return option;
              }
              if (option.inputValue) {
                return option.inputValue;
              }
              return option.label;
            }}
            renderInput={(params) => (
              <FormField
                {...params}
                label={"Choose Active Score to Display"}
                InputLabelProps={{ shrink: true }}
              />
            )}
            fullWidth
          />
        </MDBox>
      </Grid>
      <Grid>
        <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 500, width: "100%", display: ""}}/>
      </Grid>
    </Grid>
  );
}

export default RecordScoreTimeline;