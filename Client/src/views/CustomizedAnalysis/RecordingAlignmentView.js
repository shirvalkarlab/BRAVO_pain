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

function RecordingAlignmentView({nodes}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const figureTitle = "RecordingAlignmentView";

  const [alert, setAlert] = useState(null);

  const [fig, setFig] = useState(null);
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
  const [dataAlignment, setDataAlignment] = useState({
    alignment: 0,
    anchor: "",
    anchor_id: "",
  });

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, []);

  useEffect(() => {
    let channelOptions = [];
    for (let i in nodes) {
      let nodeName = nodes[i].data.Name.length > 0 ? nodes[i].data.Name : nodes[i].data.Id;
      for (let k in nodes[i].data.Metadata.ChannelNames) {
        const channelName = nodeName + " " + nodes[i].data.Device.Heritage + ": " + nodes[i].data.Metadata.ChannelNames[k];
        const channelId = nodes[i].id + "_" + nodes[i].data.Id + "_" + k;
        if (!channelOptions.map((a) => a.id).includes(channelId)) {
          channelOptions.push({
            label: channelName,
            id: channelId,
            alignment: nodes[i].data.Alignment
          });
        }
      }
    }
    setAvailableChannels({active: [], options: channelOptions})
  }, [nodes]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    const ax = fig.subplots(availableChannels.active.length, 1, {sharex: true, sharey: true});
    let subplotIds = [];
    for (let i in availableChannels.active) {
      subplotIds.push(`${availableChannels.active[i].label}`);
      fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)}`, {fontSize: 15}, ax[i]);
      fig.setSubtitle(`${availableChannels.active[i].label}`,ax[i]);
    }
    fig.setSubplotId(subplotIds);
    
    fig.setLegend({ tracegroupgap: 5, xanchor: "left", y: 0.5, });
    fig.setLayoutProps({ hovermode: "x", hoverdistance: 1 });

  }, [fig, availableChannels]);

  useEffect(() => {
    for (let i in availableChannels.active) {
      if (!data[availableChannels.active[i].id]) {
        const ids = availableChannels.active[i].id.split("_");
        SessionController.query("/api/queryTimeseriesRecording", {
          RequestType: "RawTimeseries",
          ParticipantId: participant_uid,
          RecordingId: ids[1],
          ChannelIndex: ids[2]
        }).then((response) => {
          setData({...data, 
            [availableChannels.active[i].id]: {...response.data, Alignment: availableChannels.active[i].alignment}
          });
          setAlert(null);
        }).catch((error) => {
          SessionController.displayError(error, setAlert);
        });
      }
    }

  }, [availableChannels.active])

  useEffect(() => {
    if (!fig) return;

    let graphSeries = [];
    for (let i in availableChannels.active) {
      if (data[availableChannels.active[i].id]) {
        const dataToRender = data[availableChannels.active[i].id];
        var timeArray = Array(dataToRender.Data.length).fill(0).map((value, index) => new Date(dataToRender.StartTime*1000 + dataToRender.Alignment*1000 + (1000/dataToRender.SamplingRate)*index));
        graphSeries.push({
          type: "line",
          x: timeArray, y: dataToRender.Data,
          ylim: Math.quantileSeq(Math.abs(Math.matrix(dataToRender.Data)), 0.99),
          xlim: [timeArray[0],timeArray[timeArray.length-1]], 
          options: {
            id: availableChannels.active[i].id,
            name: availableChannels.active[i].label,
            linewidth: 0.5,
            hovertemplate: `  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "uV", language)}<extra></extra>`,
          }, 
          axName: availableChannels.active[i].label
        });
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
    
    fig.traces = fig.traces.filter((a) => a.id == "alignmentLine");
    refreshRender();

    const ref = document.getElementById(figureTitle);
    if (ref) {
      ref.on("plotly_click", plotly_onClick);
      return () => {
        ref.removeListener("plotly_click", plotly_onClick);
      }
    };
  }, [fig, renderData]);

  useEffect(() => {
    if (!fig || dataAlignment.alignment == 0) return; 

    for (let i in fig.traces) {
      if (fig.traces[i].id == "alignmentLine") {
        fig.traces.splice(i,1);
        break;
      }
    }

    const subAx = fig.getAxes(dataAlignment.anchor);
    fig.plot([new Date(dataAlignment.alignment*1000), new Date(dataAlignment.alignment*1000)], fig.getYlim(subAx), {
      id: "alignmentLine",
      linewidth: 2,
      color: "#FF0000",
      hovertemplate: `<extra></extra>`,
    }, subAx);
    fig.render();
  }, [fig, dataAlignment])

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
    <DialogContent>
      {alert}
      <MDBox px={2} pt={2}>
        <MDTypography variant="h5">
          {"Edit Alignment with Visualization"}
        </MDTypography>
      </MDBox>
      
      <MDBox px={2} pt={2}>
        <Autocomplete selectOnFocus clearOnBlur multiple
          renderInput={(params) => (
            <TextField {...params} variant="standard" label={"Reference Channel Selection"}/>
          )}
          isOptionEqualToValue={(option, value) => {
            return option.id === value.id;
          }}
          renderOption={(props, option) => <li {...props}>{option.label}</li>}
          value={availableChannels.active}
          options={availableChannels.options}
          onChange={(event, newValue) => {
            if (newValue.length <= 2) setAvailableChannels({...availableChannels, active: newValue});
          }}
        />
      </MDBox>
      <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 600, width: "100%", display: ""}}
        onContextMenu={onContextMenu}
      >
        <Menu open={contextMenu !== null}
          onClose={() => setContextMenu(null)}
          anchorReference="anchorPosition"
          anchorPosition={
            contextMenu !== null
              ? { top: contextMenu.mouseY, left: contextMenu.mouseX }
              : undefined
          }
          disableScrollLock={true}
        >
          <MenuItem onClick={() => {
            setContextMenu(null);
            setDataAlignment({alignment: eventInfo.time/1000, anchor: eventInfo.channel_name, anchor_id: eventInfo.channel});
          }}>{"Set Alignment Anchor"}</MenuItem>
          <MenuItem onClick={() => {
            setContextMenu(null);
            for (let i in nodes) {
              for (let k in nodes[i].data.Metadata.ChannelNames) {
                const channelId = nodes[i].id + "_" + nodes[i].data.Id + "_" + k;
                if (channelId == eventInfo.channel) {
                  setData((data) => {
                    data[channelId].Alignment += (dataAlignment.alignment - eventInfo.time/1000);
                    return {...data}
                  });
                  nodes[i].data.Alignment += (dataAlignment.alignment - eventInfo.time/1000);
                }
              }
            }
          }}>{"Set Alignment"}</MenuItem>
        </Menu>
      </MDBox>
    </DialogContent>
  );
}

export default RecordingAlignmentView;