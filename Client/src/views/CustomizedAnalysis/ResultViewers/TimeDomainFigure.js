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

function TimeDomainFigure({dataToRender, analysisId, resultId, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);

  const [fig, setFig] = useState(null);
  const [cachedData, setCachedData] = useState([]);
  const [availableChannels, setAvailableChannels] = useState({active: [], options: []});
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
    setAvailableChannels({active: dataToRender.ActiveChannel, options: dataToRender.AllChannels});
    setCachedData(dataToRender.ActiveChannel)
  }, [dataToRender]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    const ax = fig.subplots(availableChannels.active.length, 1, {sharex: true, sharey: true});
    let subplotIds = [];
    for (let i in availableChannels.active) {
      subplotIds.push(`${availableChannels.active[i]}`);
      fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Amplitude", language)}`, {fontSize: 15}, ax[i]);
      fig.setSubtitle(`${availableChannels.active[i]}`,ax[i]);
    }
    fig.setSubplotId(subplotIds);
    
    fig.setLegend({ tracegroupgap: 5, xanchor: "left", y: 0.5, });
    fig.setLayoutProps({ hovermode: "x", hoverdistance: 1 });

  }, [fig, availableChannels]);

  useEffect(() => {
    for (let i in availableChannels.active) {
      if (!cachedData.includes(availableChannels.active[i])) {
        SessionController.query("/api/queryCustomizedAnalysis", {
          RequestType: "AnalysisOutput",
          ParticipantId: participant_uid,
          AnalysisId: analysisId,
          ResultId: resultId,
          ActiveChannels: [availableChannels.active[i]]
        }).then((response) => {
          setCachedData((cachedData) => [...cachedData, availableChannels.active[i]]);
          setData((data) => {
            data.Signal.push(...response.data.Signal);
            return {...data};
          });
        }).catch((error) => {
          SessionController.displayError(error, setAlert);
        });
      }
    }
  }, [availableChannels.active])

  useEffect(() => {
    if (!fig) return;

    let graphSeries = [];
    for (let j in availableChannels.active) {
      for (let i in data.Signal) {
        if (data.Signal[i].SignalSeries.ChannelNames == availableChannels.active[j]) {
          let timeArray = [];
          if (data.Signal[i].SignalSeries.Time) {
            timeArray = data.Signal[i].SignalSeries.Time.map((value, index) => new Date(data.Signal[i].SignalSeries.StartTime*1000 + value*1000));
          } else {
            timeArray = data.Signal[i].SignalSeries.Data.map((value, index) => new Date(data.Signal[i].SignalSeries.StartTime*1000 + index*1000 / data.Signal[i].SignalSeries.SamplingRate));
          }
          graphSeries.push({
            type: "line",
            x: timeArray, y: data.Signal[i].SignalSeries.Data,
            xlim: [timeArray[0],timeArray[timeArray.length-1]], 
            options: {
              id: availableChannels.active[j],
              name: availableChannels.active[j],
              linewidth: 0.5,
              hovertemplate: `  %{y:.2f} ${data.Signal[i].SignalSeries.Unit}<extra></extra>`,
            }, 
            axName: availableChannels.active[j]
          });
        }
      }
    }
    
    setRenderData(graphSeries);
  }, [availableChannels.active, data]);

  const refreshRender = () => {
    for (let i in renderData) {
      const subAx = fig.getAxes(renderData[i].axName);
      if (subAx) {
        if (renderData[i].type === "line") {
          fig.plot(renderData[i].x, renderData[i].y, renderData[i].options, subAx);
        }
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
      <MDBox>
        <Autocomplete selectOnFocus clearOnBlur multiple
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
            if (newValue.length <= 2) setAvailableChannels({...availableChannels, active: newValue});
          }}
        />
      </MDBox>
      <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 400*availableChannels.active.length, width: "100%", display: availableChannels.active.length == 0 ? "none" : ""}}
        onContextMenu={onContextMenu}
      />
    </MDBox>
  );
}

export default TimeDomainFigure;