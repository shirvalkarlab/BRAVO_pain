/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import {useCallback, useState, useEffect, useMemo} from "react";
import {useResizeDetector} from "react-resize-detector";
import colormap from "colormap";
import * as math from "mathjs";

import { Autocomplete, Grid, Switch, FormControlLabel } from "@mui/material";
import FormField from "components/MDInput/FormField";
import MDBox from "components/MDBox";

import { PlotlyRenderManager } from "graphing-utility/Plotly";
import { formatSegmentString, matchArray } from "database/helper-function";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";
import { SessionController } from "database/session-control";

function PowerBandBoxplot({dataToRender, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  
  const [figGroup, setFigGroup] = useState({});
  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [channel, setChannel] = useState({options: [], active: ""});
  
  const [refresh, setRefresh] = useState(0);
  const [centerFreq, setCenterFreq] = useState(22);

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
    fig.setYlim([0, 20]);
    fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)})`, {fontSize: 15});
    fig.setLayoutProps({
      hovermode: "xy",
      boxmode: "group"
    });
  }, [fig]);

  useEffect(() => {
    if (!dataToRender || !fig) return; 

    setChannel(() => {
      let channels = [];
      for (let key in dataToRender) {
        for (let type in dataToRender[key]) {
          for (let chan in dataToRender[key][type]) {
            if (!channels.includes(chan)) channels.push(chan);
          }
        }
      }

      return {options: channels, active: channels.length > 0 ? channels[0] : ""}
    });

  }, [fig, dataToRender]);

  useEffect(() => {
    if (!dataToRender || !fig) return; 

    let graphSeries = [];
    let allSettings = Object.keys(dataToRender);
    allSettings = allSettings.sort((a,b) => a.localeCompare(b));
    for (let type of ["MEDON", "MEDOFF"]) {
      let xData = [];
      let yData = [];

      for (let key of allSettings) {
        for (let chan in dataToRender[key][type]) {
          if (chan == channel.active) {
            yData.push(...dataToRender[key][type][chan]);
            xData.push(...dataToRender[key][type][chan].map((a) => key));
          }
        }
      }

      if (xData.length == 0) continue;

      graphSeries.push({
        type: "box", x: xData, y: yData,  
        options: {
          showlegend: true,
          name: type,
          fillcolor: type == "MEDON" ? "#000000" : "#AA0000",
          marker: {color: type == "MEDON" ? "#000000" : "#AA0000"},
          hovertemplate: `<extra></extra>`,
        },
      });
    }

    graphSeries = graphSeries.sort((a,b) => a.options.name.localeCompare(b.options.name))
    setRenderData(graphSeries);
  }, [fig, dataToRender, channel.active]);

  const refreshRender = (fig) => {
    for (let i in renderData) {
      if (renderData[i].type === "box") {
        fig.box(renderData[i].x, renderData[i].y, renderData[i].options);
        fig.setYlim([0, math.max(renderData[i].y)*1.1]);
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig) return;
    
    fig.traces = [];
    refreshRender(fig);

    setRefresh((refresh) => {
      return refresh += 1;
    });
  }, [figGroup, renderData]);

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
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <MDBox px={3} pt={3}>
          <Autocomplete
            value={channel.active}
            options={channel.options}
            onChange={(event, value) => setChannel({...channel, active: value})}
            renderInput={(params) => (
              <FormField
                {...params}
                label={"Channel Selector"}
                InputLabelProps={{ shrink: true }}
              />
            )}
            disableClearable
          />
        </MDBox>
      </Grid>
      <Grid key={figureTitle} item xs={12}>
        <MDBox id={figureTitle} style={{height: 800, width: "100%", paddingBottom: 15}}/>
      </Grid>
    </Grid>
  ), [refresh]);
}

export default PowerBandBoxplot;