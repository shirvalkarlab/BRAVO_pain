/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useState, useCallback, useEffect } from "react";
import { useResizeDetector } from 'react-resize-detector';

import MDBox from "components/MDBox";

import colormap from "colormap";
import { TwitterPicker, BlockPicker } from "react-color";

import { Card, Menu, MenuItem, Dialog, DialogContent, Grid, IconButton, Popover, TextField, DialogActions } from "@mui/material";
import MDTypography from "components/MDTypography";
import RadioButtonGroup from "components/RadioButtonGroup";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { dictionary, dictionaryLookup } from "assets/translation";
import { usePlatformContext } from "context";

function ParticipantEventCount({dataToRender, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [popup, setPopupState] = useState({item: ""});

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [grouping, setGrouping] = useState("Month");
  const [annotationState, setAnnotationState] = useState({});

  useEffect(() => {
    setFig(new PlotlyRenderManager(figureTitle, language));
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setYlabel("Frequency (Count)", {fontsize: 15});
    fig.setLayoutProps({ hovermode: "xy", barmode: "stack" });
    fig.setTitle("Marked Events Log");
      
    if (!fig.fresh) {
      refreshRender();
    }
  }, [fig]);

  useEffect(() => {
    setAnnotationState((annotationState) => {
      const colors = colormap({
        colormap: 'hsv',
        nshades: 12,
        format: 'hex',
        alpha: 1,
      });

      for (let i in dataToRender) {
        if (!annotationState[dataToRender[i].Name]) {
          annotationState[dataToRender[i].Name] = {show: true, color: colors[10-Object.keys(annotationState).length > 0 ? 10-Object.keys(annotationState).length : 0]}
        }
      }
      return {...annotationState}
    })
  }, [dataToRender]);

  useEffect(() => {
    if (!fig) return;

    let graphSeries = [];

    const roundedTime = dataToRender.map((a) => Math.floor(a.Date / (grouping == "Week" ? 604800 : 2592000))*(grouping == "Week" ? 604800 : 2592000));

    for (let key in annotationState) {
      if (!annotationState[key].show) continue;

      let counter = {}, xData = [];
      for (let i in dataToRender) {
        if (dataToRender[i].Name == key) {
          if (!counter[roundedTime[i]*1000]) {
            counter[roundedTime[i]*1000] = 0;
            xData.push(roundedTime[i]*1000);
          }
          counter[roundedTime[i]*1000] += 1;
        }
      }
      
      graphSeries.push({
        type: "bar", x: xData.map((a) => new Date(a+(grouping == "Week" ? 604800000/2 : 2592000000/2))), y: xData.map((a) => counter[a]),
        options: {
          facecolor: annotationState[key].color,
          width: grouping == "Week" ? 604800000 : 2592000000,
          name: key,
          meta: xData.map((a) => {
            return new Date(a).toLocaleDateString() + " - " + new Date(a+(grouping == "Week" ? 604800000 : 2592000000)).toLocaleDateString()
          }),
          text: xData.map((a) => counter[a].toFixed(0)),
          hovertemplate: "  %{meta} <br>  Count: %{y} <extra></extra>",
          showlegend: false,
        }
      });
    }

    setRenderData(graphSeries);

  }, [dataToRender, annotationState, grouping])
  
  /*
  const handleGraphing = (data, timeRange) => {

  }
  */

  const refreshRender = () => {
    for (let i in renderData) {
      if (renderData[i].type === "bar") {
        fig.bar(renderData[i].x, renderData[i].y, renderData[i].options);
      }
    }
    fig.render();
  }

  // Refresh Left Figure if Data Changed
  useEffect(() => {
    if (!fig) return;
    
    fig.traces = [];
    refreshRender();
  }, [fig, renderData, grouping]);

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
        <MDBox px={2} pb={2} display={"flex"} flexDirection={"row"}>
          <Grid container spacing={2}>
            {Object.keys(annotationState).map((name) => {
              return <Grid key={name} item xs={6} sm={4} md={3} lg={2}>
                <Card>
                <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"} px={2} py={1}>
                  <IconButton
                    style={{padding: 0, marginRight: 3, borderStyle: "solid", borderColor: "#000000", borderWidth: 1, height: "100%"}} 
                    onClick={(event) => setPopupState({item: name, anchorEl: event.currentTarget})}
                  >
                    <img style={{background: annotationState[name].color, padding: 8, borderRadius: "50%"}}/>
                  </IconButton>
                  <Popover 
                    open={popup.item == name}
                    onClose={() => setPopupState({item: "", anchorEl: null})}
                    anchorEl={popup.anchorEl}
                    anchorOrigin={{
                      vertical: 'bottom',
                      horizontal: 'left',
                    }}
                    transformOrigin={{
                      vertical: "top",
                      horizontal: 'left',
                    }}
                    PaperProps={{sx: {boxShadow: "none"}}}
                  >
                    <TwitterPicker color={annotationState[name].color} onChange={(color) => {
                      setAnnotationState((annotationState) => {
                        annotationState[name].color = color.hex;
                        return {...annotationState}
                      });
                    }}/>
                  </Popover>
                  <MDTypography variant="h6" fontSize={15} color={"dark"} style={{cursor: "pointer"}} onClick={() => {
                    setAnnotationState((annotationState) => {
                      annotationState[name].show = !annotationState[name].show;
                      return {...annotationState}
                    });
                  }}>
                    {name}
                  </MDTypography>
                </MDBox>
                </Card>
              </Grid>
            })}
          </Grid>
        </MDBox>
      </Grid>
      <Grid item xs={12}>
        <MDBox px={3} pb={2} display={"flex"} flexDirection={"row"}>
          <RadioButtonGroup row 
            defaultValue={grouping}
            value={grouping} 
            options={[
              {value: "Week", label: "By Week"},
              {value: "Month", label: "By Month"},
            ]}
            onChange={(event) => setGrouping(event.target.value)}
          />
        </MDBox>
      </Grid>
      <Grid>
        <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 500, width: "100%", display: ""}}/>
      </Grid>
    </Grid>
  );
}

export default ParticipantEventCount;