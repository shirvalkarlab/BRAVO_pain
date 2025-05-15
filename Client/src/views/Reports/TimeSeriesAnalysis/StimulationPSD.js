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

import { Autocomplete, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import FormField from "components/MDInput/FormField";

import { PlotlyRenderManager } from "graphing-utility/Plotly";
import { formatSegmentString, matchArray } from "database/helper-function";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

function StimulationPSD({dataToRender, channel, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  
  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [cacheData, setCacheData] = useState(null);
  const [options, setOptions] = useState({type: "Channel", options: [], value: ""});

  const [refresh, setRefresh] = useState(0);
  const [centerFreq, setCenterFreq] = useState(22);

  useEffect(() => {
    setFig(new PlotlyRenderManager(figureTitle, language));
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
  
    if (!fig.fresh) {
      fig.clearData();
    }
    
    fig.subplots(1, 1, {sharey: false, sharex: false});
    fig.setScaleType("log", "y");
    fig.setTickValue([0.001, 0.01, 0.1, 1, 10, 100, 1000], "y");
    fig.setYlim([-3, 2]);
    fig.setXlim([0, 100]);
    fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Frequency", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Hertz", language)})`, {fontSize: 15});
    fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)})`, {fontSize: 15});
    fig.setSubtitle("Event Averaged PSDs");

    if (!fig.fresh) {
      refreshRender(fig);
    }

  }, [fig]);

  useEffect(() => {
    setOptions((options) => {
      options.options = [];
      if (options.type == "Channel") {
        for (let trial in dataToRender.Signal) {
          if (!options.options.includes(dataToRender.Signal[trial].SignalSeries.ChannelNames)) {
            options.options.push(dataToRender.Signal[trial].SignalSeries.ChannelNames);
          }
        }
      }
      return {options: [...options.options], value: options.options.length > 0 ? options.options[0] : "", type: options.type};
    });
  }, [options.type, dataToRender, annotations]);

  useEffect(() => {
    let cacheData = {};
    for (let trial in dataToRender.Signal) {
      if (dataToRender.Signal[trial].SignalSeries.ChannelNames === channel) {
        if (!cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames]) {
          cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames] = {Base: {freq: dataToRender.Signal[trial].SignalSeries.Spectrum.Frequency}};
        }
        
        const selected_data = dataToRender.Signal[trial].SignalSeries.Spectrum.Power;
        if (!cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames].Base.power) {
          cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames].Base.power = math.matrix(selected_data);
        } else {
          cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames].Base.power = math.concat(cacheData[dataToRender.Signal[trial].SignalSeries.ChannelNames].Base.power, 
            selected_data, 1);
        }
      }
    }
    setCacheData(cacheData);    
  }, [dataToRender, channel]);

  useEffect(() => {
    const colors = colormap({
      colormap: 'rainbow',
      nshades: 101,
      format: 'hex',
      alpha: 1,
    });

    let graphSeries = [];
    if (options.type == "Channel") {
      for (let channel in cacheData) {
        if (channel == options.value) {
          let counter = 0;
          const colorMapper = (level) => colors[Math.floor(level/Object.keys(cacheData[channel]).length*100)];
          for (let annotation in cacheData[channel]) {
            if (cacheData[channel][annotation].power) {
              counter += 1;
              graphSeries.push({
                type: "line",
                x: cacheData[channel][annotation].freq, y: math.mean(cacheData[channel][annotation].power, 1)._data, error_y: math.std(cacheData[channel][annotation].power, 1)._data.map((a) => a/math.sqrt(cacheData[channel][annotation].power._size[1])),
                line_options: {
                  name: annotation,
                  legendgroup: annotation,
                  color: colorMapper(counter),
                  linewidth: 2,
                  hovertemplate: `  ${annotation}<br>  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)}<extra></extra>`,
                  showlegend: true
                }, 
                shade_options: {
                  color: colorMapper(counter),
                  alpha: 0.3,
                  legendgroup: annotation,
                  showlegend: false
                },
              });
            }
          }
        }
      }
    }
    
    setRenderData(graphSeries);    
  }, [fig, cacheData, options.value]);

  const refreshRender = (fig) => {
    for (let i in renderData) {
      if (renderData[i].type === "line") {
        fig.shadedErrorBar(renderData[i].x, renderData[i].y, renderData[i].error_y, renderData[i].line_options, renderData[i].shade_options);
      }
    }
    fig.render();
  }

  useEffect(() => {
    if (!fig) return;

    fig.traces = [];
    refreshRender(fig);

    const ref = document.getElementById(figureTitle);
    if (ref && ref.on) {
      ref.on("plotly_click", plotly_onClick);
    };
    setRefresh((refresh) => {
      return refresh += 1;
    });

    return () => {
      const ref = document.getElementById(figureTitle);
      if (ref && ref.removeListener) {
        ref.removeListener("plotly_click", plotly_onClick);
      };
    }
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

  var updateTimeout = null;
  var plotly_singleclicked = false;
  const plotly_onClick = (data) => {
    if (plotly_singleclicked) {
      plotly_singleclicked = false;
      clearTimeout(updateTimeout);
    } else {
      plotly_singleclicked = true;
      updateTimeout = setTimeout(function() {
        setCenterFreq(data["points"][0]["x"]);
        plotly_singleclicked = false
      }, 300);
    }
  };

  return useMemo(() => (
    <Grid container spacing={0}>
      <Grid key={figureTitle} item xs={12}>
        <MDBox ref={ref} id={figureTitle} style={{height: 600, width: "100%"}}/>
      </Grid>
    </Grid>
  ), [refresh]);
}

export default StimulationPSD;