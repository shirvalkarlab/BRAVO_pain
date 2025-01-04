/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
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

function MedtronicCircadianRhythm({dataToRender, annotations, showEventCount, activeChannel, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [cacheData, setCacheData] = useState({});

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
    let graphSeries = [{
      type: "line", x: [], y: [], error_y: [],
      line_options: {
        linewidth: 2,
        color: "#000000",
        hovertemplate: `  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)}<extra></extra>`,
        showlegend: false
      }, 
      shade_options: {
        color: "#000000",
        alpha: 0.3,
        showlegend: false
      }, 
    }, {
      type: "bar", x: [], y: [], options: {
        width: 600000,
        opacity: 0.3,
        facecolor: "#FF0000",
        showlegend: false,
      }
    }];

    let xData = [], yData = [], events = [];
    for (let i in dataToRender) {
      for (let j in dataToRender[i].ChannelNames) {
        if (dataToRender[i].ChannelNames[j].endsWith(" LFP")) {
          const channelName = dataToRender[i].Device.Heritage + ": " + dataToRender[i].ChannelNames[j].replace(" LFP", "");
          const therapyName = channelName + " (" + dataToRender[i].TherapyString + " Sense: " + dataToRender[i].RecordingString + ")";
          if (activeChannel == therapyName) {
            xData.push(...dataToRender[i].Time);
            yData.push(...dataToRender[i].Data[j]);
            events.push(...annotations.filter((a) => a.Date > dataToRender[i].Time[0] && a.Date < dataToRender[i].Time[dataToRender[i].Time.length-1]).map((a) => a.Date))
          }
        }
      }
    }

    const timezoneOffset = new Date().getTimezoneOffset();
    xData = xData.map((a) => math.round(((a-timezoneOffset*60) % 86400) / 600) * 600000);
    events = events.map((a) => math.round(((a-timezoneOffset*60) % 86400) / 600) * 600000);
    const inRange = (time, ref, window) => {
      if (math.abs(time - ref) < window) return true; 
      if (math.abs(time+86400 - ref) < window) return true; 
      if (math.abs(time-86400 - ref) < window) return true; 
      return false
    }

    const window = 1200000;
    const defaultTimeArray = new Array(145).fill(0).map((a,i) => i*600000);
    for (let i = 0; i < defaultTimeArray.length; i++) {
      graphSeries[0].x.push(new Date(defaultTimeArray[i]+timezoneOffset*60000));
      if (i == 0 || i == 144) {
        const windowedData = yData.filter((a,t) => inRange(xData[t],defaultTimeArray[0],window) || inRange(xData[t],defaultTimeArray[144],window));
        if (windowedData.length > 0) {
          graphSeries[0].y.push(math.mean(windowedData));
          graphSeries[0].error_y.push(math.std(windowedData)/math.sqrt(windowedData.length)*2);
        } else {
          graphSeries[0].y.push(0);
          graphSeries[0].error_y.push(0);
        }
      } else {
        const windowedData = yData.filter((a,t) => inRange(xData[t],defaultTimeArray[i],window));
        if (windowedData.length > 0) {
          graphSeries[0].y.push(math.mean(windowedData));
          graphSeries[0].error_y.push(math.std(windowedData)/math.sqrt(windowedData.length)*2);
        } else {
          graphSeries[0].y.push(0);
          graphSeries[0].error_y.push(0);
        }
      }

      graphSeries[1].x.push(new Date(defaultTimeArray[i]+timezoneOffset*60000));
      graphSeries[1].y.push(events.filter((a) => a == defaultTimeArray[i]).length);
    }
    setRenderData(graphSeries);

  }, [fig, activeChannel, annotations, dataToRender]);

  const refreshRender = () => {
    const ax = fig.getAxes();
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.shadedErrorBar(renderData[i].x, renderData[i].y, renderData[i].error_y, renderData[i].line_options, renderData[i].shade_options, ax[0]);
      } else if (renderData[i].type === "bar" && showEventCount) {
        fig.bar(renderData[i].x, renderData[i].y, renderData[i].options, ax[1]);
        fig.setYlim([0, math.max(renderData[i].y) || 1], ax[1])
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig || !renderData) return;
    
    fig.traces = [];
    refreshRender();
  }, [fig, renderData, showEventCount]);

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

export default MedtronicCircadianRhythm;