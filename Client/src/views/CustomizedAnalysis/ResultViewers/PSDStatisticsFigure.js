/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useResizeDetector } from 'react-resize-detector';

import { Menu, MenuItem, DialogContent, Autocomplete, TextField } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import * as Math from "mathjs"
import colormap from "colormap";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { SessionController } from "database/session-control";
import { dictionary, dictionaryLookup } from "assets/translation";

function PSDStatisticsFigure({dataToRender, analysisId, resultId, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);

  const [fig, setFig] = useState(null);
  const [cachedData, setCachedData] = useState([]);
  const [availableChannels, setAvailableChannels] = useState({active: "", options: []});
  const [availableTestType, setAvailableTestType] = useState({active: "", options: ["Welch's T-Statistics", "Spearman's R"]});
  const [data, setData] = useState({});
  const [renderData, setRenderData] = useState([]);
  
  const [contextMenu, setContextMenu] = useState(null);
  const [eventInfo, setEventInfo] = useState({
    name: "",
    time: 0,
    duration: 0,
    show: false
  });

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, []);

  useEffect(() => {
    setData({...dataToRender});
    let availableTests = [];
    for (let i in dataToRender.Spectrum) {
      if (!availableTests.includes(dataToRender.Spectrum[i].TestType)) {
        availableTests.push(dataToRender.Spectrum[i].TestType);
      }
    }
    setAvailableChannels({active: "", options: dataToRender.AllChannels});
    setAvailableTestType({active: "", options: availableTests});
  }, [dataToRender]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    const ax = fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Statistics", language)}`, {fontSize: 15}, ax);
    fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Frequency", language)}`, {fontSize: 15}, ax);
    
    fig.setLayoutProps({ hovermode: "x", hoverdistance: 1 });
    fig.setLegend({ tracegroupgap: 5, xanchor: "right", y: 1 });

  }, [fig, availableChannels]);

  useEffect(() => {
    
  }, [availableChannels])

  useEffect(() => {
    if (!data) return;
    if (!fig) return;

    let graphSeries = [];
    for (let i in data.Spectrum) {
      if (availableChannels.active == data.Spectrum[i].Channel) {
        if (availableTestType.active == data.Spectrum[i].TestType) {
          fig.setYlim(data.Spectrum[i].Range);
          graphSeries.push({
            type: "line",
            x: data.Spectrum[i].Frequency, y: data.Spectrum[i].Results[0],
            xlim: [data.Spectrum[i].Frequency[0],data.Spectrum[i].Frequency[data.Spectrum[i].Frequency.length-1]], 
            options: {
              id: data.Spectrum[i].TestType,
              name: data.Spectrum[i].TestType,
              linewidth: 2,
              color: "#e03131ff",
              showlegend: true,
              hovertemplate: `  stats = %{y:.2f} ${""}<extra></extra>`,
            },
          });
          graphSeries.push({
            type: "line",
            x: data.Spectrum[i].Frequency, y: data.Spectrum[i].Results[1],
            xlim: [data.Spectrum[i].Frequency[0],data.Spectrum[i].Frequency[data.Spectrum[i].Frequency.length-1]], 
            options: {
              id: data.Spectrum[i].TestType + " p-value",
              name: data.Spectrum[i].TestType + " p-value",
              linewidth: 1,
              color: "#000000ff",
              showlegend: true,
              hovertemplate: `  p = %{y:.2f} ${""}<extra></extra>`,
            },
          });
        }
      }
    }
    setRenderData(graphSeries);
  }, [availableChannels.active, availableTestType.active, data]);

  const refreshRender = () => {
    fig.traces = [];
    const ax = fig.getAxes();
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.plot(renderData[i].x, renderData[i].y, renderData[i].options, ax);
        fig.setXlim(renderData[i].xlim);
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig || !renderData) return;
    
    refreshRender();
    const ref = document.getElementById(figureTitle);
    if (ref) {
      ref.on("plotly_click", plotly_onClick);
      return () => {
        ref.removeListener("plotly_click", plotly_onClick);
      }
    };
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

  const plotly_onClick = (data) => {
    setEventInfo((eventInfo) => {
      eventInfo.channel_name = data.points[0].data.name;
      eventInfo.channel = data.points[0].data.id;
      eventInfo.current_alignment = data.points[0].data.current_alignment;
      eventInfo.time = new Date(data.points[0].x).getTime();
      return {...eventInfo};
    });
  };

  const onContextMenu = (event) => {
    event.preventDefault();
    document.getElementById(figureTitle).focus();
    setContextMenu( contextMenu === null ? { mouseX: event.clientX + 2, mouseY: event.clientY - 6, } : null );
  };

  return (
    <MDBox>
      <MDBox mb={1}>
        <Autocomplete selectOnFocus clearOnBlur
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Channel Selection"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={availableChannels.active}
          options={availableChannels.options}
          onChange={(event, newValue) => {
            setAvailableChannels({...availableChannels, active: newValue});
          }}
        />
      </MDBox>
      <MDBox>
        <Autocomplete selectOnFocus clearOnBlur
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Statistic Test Selection"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option === value;
          }}
          renderOption={(props, option) => <li {...props}>{option}</li>}
          value={availableTestType.active}
          options={availableTestType.options}
          onChange={(event, newValue) => {
            setAvailableTestType({...availableTestType, active: newValue});
          }}
        />
      </MDBox>
      <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 400, width: "100%", display: ""}}
        onContextMenu={onContextMenu}
      />
    </MDBox>
  );
}

export default PSDStatisticsFigure;