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

import * as Math from "mathjs"
import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

const filter = createFilterOptions();

function TimeFrequencyAnalysis({dataToRender, activeChannels, handleAddEvent, handleDeleteEvent, handleAdjustAlignment, annotations, height, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [contextMenu, setContextMenu] = useState(null);
  const [eventInfo, setEventInfo] = useState({ name: "", time: 0, duration: 0, show: false });
  const [dataAlignment, setDataAlignment] = useState({ show: false, alignment: 0 });
  const [coloraxis, setColorAxis] = useState({ show: false, limit: [-20,20], limit_temp: [-20,20] });

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
      fig.fresh = true;
    }

    const ax = fig.subplots(activeChannels.length * 2, 1, {sharey: false, sharex: true});
    let subplotIds = [];
    for (let i in activeChannels) {
      subplotIds.push(`${activeChannels[i]}`);
      subplotIds.push(`${activeChannels[i]} TimeFrequencyAnalysis`);

      fig.setYlim([0, 100], ax[1+i*2]);
      fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Amplitude", language)} (Unit)`, {fontSize: 15}, ax[i*2]);
      fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Frequency", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Hertz", language)})`, {fontSize: 15}, ax[1+i*2]);
      
      fig.setSubtitle(`${activeChannels[i]}`,ax[i*2]);
      fig.setSubtitle(`${activeChannels[i]} ${dictionaryLookup(dictionary.TherapeuticAnalysis.Figure, "TimeFrequencyAnalysis", language)}`,ax[i*2 + 1]);
    }
    
    fig.setSubplotId(subplotIds);
    setRefresh((a) => a+1);
  }, [fig, activeChannels]);

  useEffect(() => {
    if (!fig) return;

    let graphSeries = [];
    for (let i in activeChannels) {
      for (let trial in dataToRender.Signal) {
        if (dataToRender.Signal[trial].SignalSeries.ChannelNames == activeChannels[i]) {
          var timeArray = Array(dataToRender.Signal[trial].SignalSeries.Data.length).fill(0).map((value, index) => new Date(dataToRender.Signal[trial].SignalSeries.StartTime*1000 + dataToRender.Signal[trial].Alignment*1000 + (1000/dataToRender.Signal[trial].SignalSeries.SamplingRate)*index));
          graphSeries.push({
            type: "line",
            x: timeArray, y: dataToRender.Signal[trial].SignalSeries.Data,
            ylim: Math.quantileSeq(Math.abs(Math.matrix(dataToRender.Signal[trial].SignalSeries.Data)), 0.99),
            xlim: [timeArray[0],timeArray[timeArray.length-1]], 
            options: {
              id: dataToRender.Signal[trial].RecordingId,
              current_alignment: dataToRender.Signal[trial].Alignment*1000,
              name: activeChannels[i],
              linewidth: 0.5,
              hovertemplate: `  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "uV", language)}<extra></extra>`,
            }, 
            axName: activeChannels[i]
          });
          
          var timeArray = Array(dataToRender.Signal[trial].SignalSeries.Spectrum.Time.length).fill(0).map((value, index) => new Date(dataToRender.Signal[trial].SignalSeries.StartTime*1000 + dataToRender.Signal[trial].SignalSeries.Spectrum.Time[index]*1000 + dataToRender.Signal[trial].Alignment*1000));

          const meanPower = Math.quantileSeq(dataToRender.Signal[trial].SignalSeries.Spectrum.Power, [0.5, 0.5]).map((a) => 10*Math.log10(a));
          //const meanPower = [0,40];
          graphSeries.push({
            type: "surf",
            x: timeArray, y: dataToRender.Signal[trial].SignalSeries.Spectrum.Frequency, z: dataToRender.Signal[trial].SignalSeries.Spectrum.Power.map((a) => {
              return a.map((b) => 10*Math.log10(b));
            }),
            options: {
              zlim: coloraxis.limit,
              hovertemplate: `  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "Hertz", language)}<br>  %{x} <br>  %{z:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "dB", language)} <extra></extra>`,
            }, 
            axName: activeChannels[i] + " " + "TimeFrequencyAnalysis"
          });
          
          if (dataToRender.Signal[trial].Alignment != 0) {
            graphSeries.push({
              type: "shading",
              x: [new Date(dataToRender.Signal[trial].SignalSeries.StartTime*1000 + dataToRender.Signal[trial].Alignment*1000), new Date(dataToRender.Signal[trial].SignalSeries.StartTime*1000)],
              xDot: [new Date(dataToRender.Signal[trial].SignalSeries.StartTime*1000)],
              y: [-100,100],
              yDot: [0],
              options: {
                size: 10,
                color: "#00ff00", 
                alpha: 0.3, 
                hovertemplate: ` Shifted Alignment ${dataToRender.Signal[trial].Alignment*1000}ms <extra></extra>`,
                name: "Shifted Alignment"
              }, 
              axName: activeChannels[i]
            })
          }
        }
      }
    }
    
    for (let j in activeChannels) {
      for (let i in annotations) {
        graphSeries.push({
          type: "shading",
          x: [new Date(annotations[i].Date*1000), new Date((annotations[i].Date+annotations[i].Duration)*1000)],
          xDot: [new Date(annotations[i].Date*1000)],
          y: [-100,100],
          yDot: [0],
          options: {
            size: 10,
            color: "#ff0000", 
            alpha: 0.3, 
            hovertemplate: ` ${annotations[i].Name}<br>  %{x} <extra></extra>`,
            name: annotations[i].Name
          }, 
          axName: activeChannels[j]
        })
      }
    }
    
    setRenderData(graphSeries);
  }, [fig, dataToRender, coloraxis.limit, annotations]);

  const refreshRender = () => {
    let caxis = fig.getColorAxis();
    for (let i in caxis) {
      fig.setColorAxis(null, caxis[i]);
    }

    for (let i in renderData) {
      const subAx = fig.getAxes(renderData[i].axName);

      if (subAx) {
        if (renderData[i].type === "line") {
          fig.plot(renderData[i].x, renderData[i].y, renderData[i].options, subAx);
        } else if (renderData[i].type === "surf") {
          const caxis = fig.createColorAxis({
            colorscale: "Jet",
            colorbar: {y: (subAx.ydomain[0]+subAx.ydomain[1])/2, len: subAx.ydomain[1]-subAx.ydomain[0]},
            clim: renderData[i].options.zlim,
          });

          fig.surf(renderData[i].x, renderData[i].y, renderData[i].z, {...renderData[i].options,
            coloraxis: caxis
          }, subAx);

        } else if (renderData[i].type === "shading") {
          fig.addShadedArea(renderData[i].x, renderData[i].y, {...renderData[i].options, hovertemplate: "<extra></extra>"}, subAx);
          fig.scatter(renderData[i].xDot, renderData[i].yDot, renderData[i].options, subAx);
        }
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig || !renderData) return;
    
    fig.traces = [];
    refreshRender();
    
    const ref = document.getElementById(figureTitle);
    if (ref) {
      ref.on("plotly_click", plotly_onClick);
      return () => {
        ref.removeListener("plotly_click", plotly_onClick);
      }
    };
  }, [fig, refresh, renderData]);

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

  return useMemo(() => (
    <MDBox ref={ref} id={figureTitle} onContextMenu={onContextMenu} 
      style={{marginTop: 5, marginBottom: 10, height: activeChannels.length*900, width: "100%", display: activeChannels.length > 0 ? "" : "none"}}
    >
      <Menu
        open={contextMenu !== null}
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
          if (eventInfo.time) setEventInfo({...eventInfo, name: "", show: true});
        }}>{"Add New Event"}</MenuItem>
        <MenuItem onClick={() => {
          setContextMenu(null);
          handleDeleteEvent(eventInfo);
          }}>{"Delete Event"}</MenuItem>
        <MenuItem onClick={() => {
          setContextMenu(null);
          if (eventInfo.channel) {
            setDataAlignment({...dataAlignment, alignment: eventInfo.current_alignment, show: true})
          };
          }}>{"Adjust Alignment"}</MenuItem>
        <MenuItem onClick={() => {
          setContextMenu(null);
          setColorAxis({...coloraxis, limit_temp: coloraxis.limit, show: true});
          }}>{"Adjust Colormap"}</MenuItem>
      </Menu>
      <Dialog open={eventInfo.show} onClose={() => setEventInfo({...eventInfo, show: false})}>
        <MDBox px={2} pt={2} sx={{minWidth: 500}}>
          <MDTypography variant="h5">
            {"New Custom Event"} 
          </MDTypography>
          <MDTypography variant="h6">
            {"Time: "}{new Date(eventInfo.time).toLocaleString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              timeZoneName: "longGeneric"
            })} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <Grid container spacing={2}>
            <Grid item xs={12} style={{display: "flex", flexDirection: "column"}}>
              <TextField
                variant="standard"
                margin="dense"
                id={"event-annotation"}
                type={"text"}
                label="Annotation Name"
                placeholder={"Annotation Name"}
                value={eventInfo.name}
                onChange={(event) => setEventInfo({...eventInfo, name: event.target.value})}
              />
            </Grid>
            <Grid item xs={12} style={{display: "flex", flexDirection: "column"}}>
              <TextField
                variant="standard"
                margin="dense"
                type={"number"}
                label="Event Duration"
                placeholder={"0 for Instant Event"}
                value={eventInfo.duration}
                onChange={(event) => setEventInfo({...eventInfo, duration: event.target.value})}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setEventInfo({...eventInfo, show: false})}>Cancel</MDButton>
          <MDButton color="info" onClick={() => {
            handleAddEvent(eventInfo);
            setEventInfo({...eventInfo, show: false});
          }}>Add</MDButton>
        </DialogActions>
      </Dialog>
      
      <Dialog open={coloraxis.show} onClose={() => setColorAxis({...coloraxis, show: false})}>
        <MDBox px={2} pt={2} sx={{minWidth: 500}}>
          <MDTypography variant="h5">
            {"Set Colorbar Axis Range (View Only)"} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} style={{display: "flex", flexDirection: "column"}}>
              <TextField
                variant="standard"
                margin="dense"
                id={"caxis-lowerlimit"}
                type={"number"}
                label="Lower Limit"
                placeholder={"Lower Limit"}
                value={coloraxis.limit_temp[0]}
                onChange={(event) => {
                  console.log(event.target.value)
                  setColorAxis({...coloraxis, limit_temp: [event.target.value, coloraxis.limit_temp[1]]})
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} style={{display: "flex", flexDirection: "column"}}>
              <TextField
                variant="standard"
                margin="dense"
                id={"caxis-upperlimit"}
                type={"number"}
                label="Upper Limit"
                placeholder={"Upper Limit"}
                value={coloraxis.limit_temp[1]}
                onChange={(event) => setColorAxis({...coloraxis, limit_temp: [coloraxis.limit_temp[0], event.target.value]})}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setEventInfo({...eventInfo, show: false})}>Cancel</MDButton>
          <MDButton color="info" onClick={() => {
            setColorAxis({...coloraxis, limit: coloraxis.limit_temp, show: false});
          }}>Set</MDButton>
        </DialogActions>
      </Dialog>
      
      <Dialog open={dataAlignment.show} onClose={() => setDataAlignment({show: false, alignment: 0})}>
        <MDBox px={2} pt={2}>
          <MDTypography variant="h5">
            {"Shift Alignment for "}{eventInfo.channel_name} 
          </MDTypography>
        </MDBox>
        <DialogContent>
          <TextField
            variant="standard"
            margin="dense"
            type={"number"}
            label="Time Shift toward Right (ms)"
            placeholder={"Enter Time Shift to be applied to " + eventInfo.channel_name}
            value={dataAlignment.alignment}
            onChange={(event) => setDataAlignment({...dataAlignment, alignment: event.target.value})}
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <MDButton color="secondary" onClick={() => setDataAlignment({...dataAlignment, show: false})}>Cancel</MDButton>
          <MDButton color="info" onClick={() => {
            setDataAlignment({...dataAlignment, show: false})
            handleAdjustAlignment(dataAlignment, eventInfo);
          }}>Add</MDButton>
        </DialogActions>
      </Dialog>
    </MDBox>
  ), [renderData, activeChannels, coloraxis, eventInfo, dataAlignment, contextMenu]);
}

export default TimeFrequencyAnalysis;