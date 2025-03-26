/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useCallback, useEffect, useState, useMemo } from "react";
import { useResizeDetector } from 'react-resize-detector';

import { Card, Grid } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import colormap from "colormap";

import { PlotlyRenderManager } from "graphing-utility/Plotly";
import { formatSegmentString, matchArray } from "database/helper-function";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";
import { SessionController } from "database/session-control";

function TherapyHistoryFigure({dataToRender, height, onTimeClick, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [fig, setFig] = useState(null);
  const [graphingData, setGraphingData] = useState(false);
  const [showDevice, setShowDevice] = useState([]);
  
  const colors = colormap({
    colormap: 'rainbow-soft',
    nshades: 11,
    format: 'hex',
    alpha: 1,
  });
  const step = Math.floor(11 / Object.keys(dataToRender.TherapyDevices).length);

  useEffect(() => {
    setShowDevice(dataToRender.TherapyDevices.map((a) => a.Id));
  }, []);

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
    
    fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setXlabel("Time (local time)", {fontSize: 15});
    fig.setAxisProps({
      zeroline: false
    }, "y");
    fig.setTitle(dictionaryLookup(dictionary.TherapyHistory.Figure, "TherapyChangeLog", language));

    fig.setLegend({
      bgcolor: "transparent",
      xanchor: "left"
    })
    fig.setLayoutProps({
      hovermode: "x"
    });
  }, [fig]);

  useEffect(() => {
    if (!fig) return;

    let graphingData = []
    for (let i in dataToRender.TherapyModification) {
      let TherapyBlocks = [];
      let TherapyChangeHistory = dataToRender.TherapyModification[i].History.filter((a) => a.Type == "TherapyChangeGroup").sort((a,b) => a.Date-b.Date);
      
      for (let j in TherapyChangeHistory) {
        if (TherapyChangeHistory[j].Date < dataToRender.TherapyModification[i].Device.Date) {
          TherapyChangeHistory[j].Date = dataToRender.TherapyModification[i].Device.Date;
        }
        if (j > 0) {
          if (TherapyChangeHistory[j-1].New == TherapyChangeHistory[j].Previous) {
            TherapyBlocks.push({
              label: TherapyChangeHistory[j-1].New,
              start: TherapyChangeHistory[j-1].Date,
              end: TherapyChangeHistory[j].Date,
              solid: true
            });
          } else {
            TherapyBlocks.push({
              label: TherapyChangeHistory[j-1].New,
              start: TherapyChangeHistory[j-1].Date,
              end: TherapyChangeHistory[j-1].Date + 24*3600 > TherapyChangeHistory[j].Date ? (TherapyChangeHistory[j-1].Date + 12*3600) : (TherapyChangeHistory[j-1].Date + 24*3600),
              solid: false
            });
            TherapyBlocks.push({
              label: TherapyChangeHistory[j].Previous,
              start: TherapyChangeHistory[j].Date - 24*3600 > TherapyChangeHistory[j-1].Date ? (TherapyChangeHistory[j].Date - 24*3600) : (TherapyChangeHistory[j].Date - 12*3600),
              end: TherapyChangeHistory[j].Date,
              solid: false
            });
          }
        }
      }

      graphingData.push({
        device: dataToRender.TherapyModification[i].Device,
        therapyBlocks: TherapyBlocks
      });

      TherapyChangeHistory = dataToRender.TherapyModification[i].History.filter((a) => a.Type === "AdaptiveTherapyStatus").sort((a,b) => a.Date-b.Date);
      let therapyStatusBlock = [];
      for (let j in TherapyChangeHistory) {
        if (TherapyChangeHistory[j].Date < dataToRender.TherapyModification[i].Device.Date) {
          TherapyChangeHistory[j].Date = dataToRender.TherapyModification[i].Device.Date;
        }
        if (j > 0) {
          if (TherapyChangeHistory[j-1].New == TherapyChangeHistory[j].Previous && TherapyChangeHistory[j-1].New == "OFF") {
            therapyStatusBlock.push({
              label: TherapyChangeHistory[j-1].New,
              start: TherapyChangeHistory[j-1].Date,
              end: TherapyChangeHistory[j].Date,
              type: TherapyChangeHistory[j].Type,
              solid: true
            });
          } 
        }
      }
      graphingData.push({
        device: dataToRender.TherapyModification[i].Device,
        therapyStatus: therapyStatusBlock
      });
      
      TherapyChangeHistory = dataToRender.TherapyModification[i].History.filter((a) => a.Type === "TherapyStatus").sort((a,b) => a.Date-b.Date);
      therapyStatusBlock = [];
      for (let j in TherapyChangeHistory) {
        if (TherapyChangeHistory[j].Date < dataToRender.TherapyModification[i].Device.Date) {
          TherapyChangeHistory[j].Date = dataToRender.TherapyModification[i].Device.Date;
        }
        if (j > 0) {
          if (TherapyChangeHistory[j-1].New == TherapyChangeHistory[j].Previous && TherapyChangeHistory[j-1].New == "OFF") {
            therapyStatusBlock.push({
              label: TherapyChangeHistory[j-1].New,
              start: TherapyChangeHistory[j-1].Date,
              end: TherapyChangeHistory[j].Date,
              type: TherapyChangeHistory[j].Type,
              solid: true
            });
          } 
        }
      }
      graphingData.push({
        device: dataToRender.TherapyModification[i].Device,
        therapyStatus: therapyStatusBlock
      });
    }
    
    setGraphingData(graphingData);
  }, [fig, dataToRender])

  // Refresh Left Figure if Data Changed
  useEffect(() => {
    if (!graphingData) return;
    
    const data = graphingData;
    let uniqueGroups = [];
    for (let i in data) {
      for (let j in data[i].therapyBlocks) { 
        if (!uniqueGroups.includes(graphingData[i].therapyBlocks[j].label)) uniqueGroups.push(graphingData[i].therapyBlocks[j].label)
      }
    }
    uniqueGroups = uniqueGroups.sort();
    fig.setTickValue(uniqueGroups.map((value, index) => index), "y");
    fig.setTickLabel(uniqueGroups.map((value, index) => value), "y");
    
    for (let i in data) {
      if (showDevice.includes(data[i].device.Id)) {
        for (let j in data[i].therapyStatus) {
          fig.addShadedArea([new Date(data[i].therapyStatus[j].start*1000), new Date(data[i].therapyStatus[j].end*1000)], [-1,5], {
            size: 10,
            color: data[i].therapyStatus[j].type === "TherapyStatus" ? "#ff0000" : "#ff00ff", 
            alpha: 0.3, 
            hovertemplate: `<extra></extra>`,
            name: "Therapy OFF"
          });
          fig.scatter(new Date(data[i].therapyStatus[j].start*1000), 2.5, {
            size: 15,
            color: data[i].therapyStatus[j].type === "TherapyStatus" ? "#ff0000" : "#ff00ff",
            alpha: 0.3, 
            hovertemplate: `Therapy OFF<extra></extra>`,
            name: "Therapy OFF"
          });

        }
      }
    }

    let therapyBlocks = [];
    let xLim = [0,0]
    for (let i in data) {
      if (showDevice.includes(data[i].device.Id)) {
        for (let j in data[i].therapyBlocks) {
          if (data[i].therapyBlocks[j].solid) {
            therapyBlocks.push({
              type: "rect",
              xref: 'x',
              x0: new Date(data[i].therapyBlocks[j].start*1000),
              x1: new Date(data[i].therapyBlocks[j].end*1000),
              y0: uniqueGroups.indexOf(data[i].therapyBlocks[j].label) - 0.3,
              y1: uniqueGroups.indexOf(data[i].therapyBlocks[j].label) + 0.3,
              line: { color: "#000000", width: 2 },
              fillcolor: colors[i*step],
              opacity: 0.6
            });
          }
          if (xLim[0] == 0 || xLim[0] > data[i].therapyBlocks[j].start) xLim[0] = data[i].therapyBlocks[j].start;
          if (xLim[1] == 0 || xLim[1] < data[i].therapyBlocks[j].end) xLim[1] = data[i].therapyBlocks[j].end;
        }
      }
    }

    fig.setLayoutProps({
      shapes: therapyBlocks,
      xaxis: {type: "date"}
    });
    fig.setXlim([new Date(xLim[0]*1000), new Date(xLim[1]*1000)]);
    fig.setYlim([-0.5, uniqueGroups.length-0.5]);

    fig.render();

    const ref = document.getElementById(figureTitle);
    if (ref) {
      ref.addEventListener("click", fig.onClick);
      document.addEventListener("PlotlyClick", onClick);
      return () => {
        ref.removeEventListener("click", fig.onClick);
        document.removeEventListener("PlotlyClick", onClick);
      }
    };
  }, [dataToRender, graphingData, showDevice, language]);

  var updateTimeout = null;
  var singleClicked = false;
  const onClick = (evt) => {
    if (singleClicked) {
      singleClicked = false;
      clearTimeout(updateTimeout);
    } else {
      singleClicked = true;
      updateTimeout = setTimeout(function() {
        plotly_onClick(evt);
        singleClicked = false
      }, 200);
    }
  };

  const plotly_onClick = (evt) => {
    const timeClicked = new Date(evt.detail.x).getTime()/1000;
    let TherapyId = "";
    let lastGroupTime = 0;
    for (let i in dataToRender.TherapyModification) {
      if (!showDevice.includes(dataToRender.TherapyModification[i].Device.Id)) continue;

      for (let j in dataToRender.TherapyModification[i].History) {
        if (dataToRender.TherapyModification[i].History[j].Date < timeClicked) {
          if (dataToRender.TherapyModification[i].History[j].Date > lastGroupTime) {
            lastGroupTime = dataToRender.TherapyModification[i].History[j].Date;
            TherapyId = dataToRender.TherapyModification[i].History[j].New;
          }
        }
      }
    }
    onTimeClick(timeClicked, TherapyId);
  }

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
    <MDBox>
      <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: height, width: "100%", display: ""}}/>
      {dataToRender ? (
        <Grid container spacing={2}>
          {dataToRender.TherapyDevices.map((device, index) => {
            return <Grid item xs={4} sm={3} key={device.Id}>
              <Card style={{cursor: "pointer", background: showDevice.includes(device.Id) ? "" : "darkgrey"}} onClick={() => {
                setShowDevice((showDevice) => {
                  if (showDevice.includes(device.Id)) showDevice = showDevice.filter((a) => a != device.Id)
                  else showDevice.push(device.Id);
                  return [...showDevice];
                })
              }}>
                <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} py={2} px={2}>
                  <MDBox style={{backgroundColor: colors[index*step], height: "10px", width: "10px", marginRight: 5}} />
                  <MDTypography fontSize={18} fontFamily={"lato"} fontWeight={"bold"} style={{textDecoration: showDevice.includes(device.Id) ? "" : "line-through"}}>
                    {device.Name.length > 15 ? device.Name.slice(0,15) : device.Name}
                  </MDTypography>
                </MDBox>
              </Card>
            </Grid>
          })}
        </Grid>
      ) : null}
    </MDBox>
  ), [showDevice, dataToRender]);
}

export default TherapyHistoryFigure;