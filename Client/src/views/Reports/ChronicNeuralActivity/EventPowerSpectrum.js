/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useCallback, useState, useEffect, useMemo } from "react";
import { useResizeDetector } from 'react-resize-detector';

import LoadingProgress from "components/LoadingProgress";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import { Autocomplete, Dialog, DialogContent, TextField, DialogActions, Grid, Menu, MenuItem } from "@mui/material";
import { createFilterOptions } from "@mui/material/Autocomplete";

import * as math from "mathjs"
import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

const filter = createFilterOptions();

function EventPowerSpectrum({dataToRender, activeChannel, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    fig.subplots(1, 1, {sharey: false, sharex: false});
    fig.setYlim([0, 10]);
    fig.setXlim([0, 100]);
    fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Frequency", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Hertz", language)})`, {fontSize: 15});
    fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)})`, {fontSize: 15});

    if (!fig.fresh) {
      refreshRender();
    }

  }, [fig]);

  useEffect(() => {
    if (!fig) return;
    let graphSeries = [];

    let events = {}
    for (let i in dataToRender) {
      for (let j in dataToRender[i].EventPSDs) {
        if (dataToRender[i].EventPSDs[j].TherapyLabel == activeChannel) {
          if (!events[dataToRender[i].Name]) {
            events[dataToRender[i].Name] = {"Frequency": dataToRender[i].EventPSDs[j].Frequency, "Power": []};
          }
          events[dataToRender[i].Name].Power.push(dataToRender[i].EventPSDs[j].Power);
        }
      }
    }

    const colors = ["#f44336", "#9c27b0", "#2196f3", "#4caf50", "#ffc107", "#b23c17",
                    "#f44336", "#9c27b0", "#2196f3", "#4caf50", "#ffc107", "#b23c17"]

    let count = 0;
    for (let key in events) {
      events[key].Power = math.matrix(events[key].Power);
      graphSeries.push({
        type: "line", x: events[key].Frequency, y: math.mean(events[key].Power,0)._data, error_y: math.std(events[key].Power,0)._data,
        line_options: {
          linewidth: 2,
          name: key + " (n=" + events[key].Power._size[0].toFixed(0) + ")",
          legendgroup: key,
          color: colors[count],
          hovertemplate: `  ${key}<br>  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)}<extra></extra>`,
          showlegend: true
        }, 
        shade_options: {
          legendgroup: key,
          color: colors[count],
          alpha: 0.3,
          showlegend: false
        },
      });
      count += 1;
    }
    
    setRenderData(graphSeries);

  }, [fig, activeChannel, dataToRender]);

  const refreshRender = () => {
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.shadedErrorBar(renderData[i].x, renderData[i].y, renderData[i].error_y, renderData[i].line_options, renderData[i].shade_options);
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig || !renderData) return;
    
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

  return useMemo(() => (
    <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 600, width: "100%", display: ""}}/>
  ), [renderData]);
}

export default EventPowerSpectrum;