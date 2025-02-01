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

function MedtronicEventRelatedPower({dataToRender, annotations, activeChannel, annotationState, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [window, setWindow] = useState(15);

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    const ax = fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Time", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Local", language)})`, {fontSize: 15}, ax[0]);
    fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)})`, {fontSize: 15}, ax[0]);
    fig.setLayoutProps({
      hovermode: "xy"
    });

    fig.addDualYAxis(ax[0]);
    fig.setYlabel("Event Count", {fontSize: 15}, ax[1]);
    fig.setAxisProps({
      title: {
        font: {
          color: "#FF0000"
        }
      },
      tickcolor:  "#FF0000",
      tickfont: {
        color: "#FF0000"
      },
      showgrid: false
    }, "y", ax[1]);

    fig.setAxisProps({
      tickformat: "%H:%M"
    }, "x", ax[0])
    
    if (!fig.fresh) {
      refreshRender();
    }

  }, [fig]);

  useEffect(() => {
    if (!fig) return;
    let graphSeries = [];

    let EventRelatedPowers = {};
    for (let i in dataToRender) {
      for (let j in dataToRender[i].ChannelNames) {
        if (dataToRender[i].ChannelNames[j].endsWith(" LFP")) {
          const channelName = dataToRender[i].Device.Heritage + ": " + dataToRender[i].ChannelNames[j].replace(" LFP", "");
          const therapyName = channelName + " (" + dataToRender[i].TherapyString + " Sense: " + dataToRender[i].RecordingString + ")";
          if (activeChannel == therapyName) {
            annotations.filter((a) => a.Date > dataToRender[i].Time[0] && a.Date < dataToRender[i].Time[dataToRender[i].Time.length-1]).map((a) => {
              if (!EventRelatedPowers[a.Name]) {
                EventRelatedPowers[a.Name] = [];
              }
              const EventPower = dataToRender[i].Data[j].filter((b,k) => dataToRender[i].Time[k] > a.Date - window*600 && dataToRender[i].Time[k] < a.Date + window*600);
              if (EventPower.length == window*2) EventRelatedPowers[a.Name].push(EventPower)
            });
          }
        }
      }
    }

    const TimeWindow = new Array(window*2).fill(0).map((_,i) => (i-window) * 600-300)
    for (let key in EventRelatedPowers) {
      if (EventRelatedPowers[key].length == 0) continue;
      const matrix = math.matrix(EventRelatedPowers[key]);
      graphSeries.push({
        type: "line", x: TimeWindow, y: math.mean(matrix,0)._data, error_y: math.std(matrix,0)._data.map((a) => a/math.sqrt(matrix._size[1])),
        line_options: {
          linewidth: 2,
          color: annotationState[key] ? annotationState[key].color : "#000000",
          hovertemplate: `  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)}<extra></extra>`,
          showlegend: false
        }, 
        shade_options: {
          color: annotationState[key] ? annotationState[key].color : "#000000",
          alpha: 0.3,
          showlegend: false
        }, 
      })
    }
    
    setRenderData(graphSeries);
  }, [fig, activeChannel, annotations, annotationState, dataToRender]);

  const refreshRender = () => {
    const ax = fig.getAxes();
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.shadedErrorBar(renderData[i].x, renderData[i].y, renderData[i].error_y, renderData[i].line_options, renderData[i].shade_options, ax[0]);
      } else if (renderData[i].type === "bar") {
        
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

export default MedtronicEventRelatedPower;