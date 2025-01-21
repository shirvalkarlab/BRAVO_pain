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

function StimulationPSD({dataToRender, activeChannels, onCenterFrequencyChange, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  
  const [figGroup, setFigGroup] = useState({});
  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [cacheData, setCacheData] = useState(null);
  const [therapyLabel, setTherapyLabel] = useState({});
  const [parameter, setParameter] = useState("Amplitude");

  const [refresh, setRefresh] = useState(0);
  const [centerFreq, setCenterFreq] = useState(22);

  useEffect(() => {
    let newGroup = {};
    for (let i in dataToRender.AllChannels) {
      if (!figGroup[dataToRender.AllChannels[i]]) {
        newGroup[dataToRender.AllChannels[i]] = new PlotlyRenderManager(figureTitle + "_" + dataToRender.AllChannels[i], language);
        newGroup[dataToRender.AllChannels[i] + "Boxplot"] = new PlotlyRenderManager(figureTitle + "Boxplot_" + dataToRender.AllChannels[i], language);
      } else {
        newGroup[dataToRender.AllChannels[i]] = figGroup[dataToRender.AllChannels[i]];
        newGroup[dataToRender.AllChannels[i] + "Boxplot"] = figGroup[dataToRender.AllChannels[i] + "Boxplot"];
      }
    }
    setFigGroup(newGroup);
    setTherapyLabel({})
  }, [figureTitle, activeChannels, dataToRender]);

  useEffect(() => {
    for (let key in figGroup) {
      const fig = figGroup[key];
      if (!fig.fresh) {
        fig.clearData();
      }
      
      if (key.endsWith("Boxplot")) {
        fig.subplots(1, 1, {sharey: false, sharex: false});
        fig.setYlim([0, 20]);
        fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)})`, {fontSize: 15});
        fig.setLayoutProps({
          hovermode: "xy"
        });

      } else {
        fig.subplots(1, 1, {sharey: false, sharex: false});
        fig.setScaleType("log", "y");
        fig.setTickValue([0.001, 0.01, 0.1, 1, 10, 100, 1000], "y");
        fig.setYlim([-3, 2]);
        fig.setXlim([0, 100]);
        fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Frequency", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Hertz", language)})`, {fontSize: 15});
        fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)})`, {fontSize: 15});
        fig.setSubtitle(key);

      }
      if (!fig.fresh) {
        refreshRender(fig, key);
      }
    }
  }, [figGroup]);

  const getTherapyChanges = (key) => {

    let modifiedParameters = [];
    let previousState = {};
    let therapySeries = {};
    for (let i in dataToRender.Therapy) {
      for (let j in dataToRender.Therapy[i].TherapySeries) {
        if (dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key]) {
          if (dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key].Type == "StandardIPGStimulation") {
            let parameters = ["Amplitude", "Frequency", "Pulsewidth"];
            for (let parameter of parameters) {
              if (previousState[parameter] === undefined) {
                therapySeries[parameter] = [{time: dataToRender.Therapy[i].TherapySeries[j].Time, state: dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key][parameter]}]
              } else {
                if (dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key][parameter] != previousState[parameter]) {
                  modifiedParameters.push(parameter)
                  therapySeries[parameter].push({time: dataToRender.Therapy[i].TherapySeries[j].Time, state: dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key][parameter]})
                }
              }
              previousState[parameter] = dataToRender.Therapy[i].TherapySeries[j].TherapyOverview[key][parameter];
            }
          }
        }
      }
    }

    return therapySeries;
  }

  useEffect(() => {
    let cacheData = {};
    
    // Extract PSDs
    for (let i in dataToRender.Signal) {
      const therapySeries = getTherapyChanges(therapyLabel[dataToRender.Signal[i].SignalSeries.ChannelNames] ? therapyLabel[dataToRender.Signal[i].SignalSeries.ChannelNames] : dataToRender.Signal[i].SignalSeries.ChannelNames)
      cacheData[dataToRender.Signal[i].SignalSeries.ChannelNames] = JSON.parse(JSON.stringify(therapySeries));
      if (therapySeries[parameter].length > 1) {
        for (let stage = 0; stage < therapySeries[parameter].length; stage++) {
          const selected_data = dataToRender.Signal[i].SignalSeries.Spectrum.Power.map((a) => {
            return a.filter((b,t) => {
              const currentTime = dataToRender.Signal[i].SignalSeries.Spectrum.Time[t] + dataToRender.Signal[i].SignalSeries.StartTime;
              return (currentTime > therapySeries[parameter][stage].time+2) && (
                (stage+1 >= therapySeries[parameter].length) ? true : (currentTime < therapySeries[parameter][stage+1].time-2)
              );
            })
          });
          if (selected_data[0].length > 0) {
            cacheData[dataToRender.Signal[i].SignalSeries.ChannelNames][parameter][stage].freq = dataToRender.Signal[i].SignalSeries.Spectrum.Frequency;
            cacheData[dataToRender.Signal[i].SignalSeries.ChannelNames][parameter][stage].power = math.matrix(selected_data);
          }
        }
      } else if (therapySeries[parameter].length == 1) {
        cacheData[dataToRender.Signal[i].SignalSeries.ChannelNames][parameter][0].freq = dataToRender.Signal[i].SignalSeries.Spectrum.Frequency;
        cacheData[dataToRender.Signal[i].SignalSeries.ChannelNames][parameter][0].power = math.matrix(dataToRender.Signal[i].SignalSeries.Spectrum.Power);
      }
    }

    setCacheData(cacheData);
  }, [figGroup, parameter, therapyLabel, dataToRender]);

  useEffect(() => {
    let graphSeries = [];

    for (let key in cacheData) {
      const therapySeries = cacheData[key];

      // Calculate Average PSDs
      for (let parameter in therapySeries) {
        const colors = colormap({
          colormap: 'jet',
          nshades: 101,
          format: 'hex',
          alpha: 1,
        });

        const maxColor = math.max(therapySeries[parameter].map((a) => a.state*10));
        const colorMapper = (level) => colors[Math.floor(level/maxColor*100)];
        for (let stage in therapySeries[parameter]) {
          if (therapySeries[parameter][stage].freq) {
            
            graphSeries.push({
              type: "line",
              x: therapySeries[parameter][stage].freq, y: math.mean(therapySeries[parameter][stage].power, 1)._data,
              options: {
                id: parameter + ": " + therapySeries[parameter][stage].state,
                name: parameter + ": " + therapySeries[parameter][stage].state.toFixed(1),
                color: colorMapper(therapySeries[parameter][stage].state*10),
                linewidth: 2,
                hovertemplate: `  ${parameter + ": " + therapySeries[parameter][stage].state.toFixed(1)}<br>  %{y:.2f} ${dictionaryLookup(dictionary.FigureStandardUnit, "uV2Hz", language)}<extra></extra>`,
                showlegend: true
              }, 
              figName: key
            });
          }
        }
      }
      
      const getFrequencyIndex = (freq) => {
        for (let i = 0; i < freq.length; i++) {
          if (freq[i] >= centerFreq) return i;
        }
      }

      for (let parameter in therapySeries) {
        let xData = [], yData = [];
        for (let stage in therapySeries[parameter]) {
          if (therapySeries[parameter][stage].freq) {
            const centerIndex = getFrequencyIndex(therapySeries[parameter][stage].freq);
            xData.push(...therapySeries[parameter][stage].power._data[centerIndex].map((a) => therapySeries[parameter][stage].state));
            yData.push(...therapySeries[parameter][stage].power._data[centerIndex]);
          }
        }
        
        if (yData.length > 0) {
          graphSeries.push({
            type: "box",
            x: xData, y: yData, 
            parameter: parameter,
            options: {
              width: 0.2,
              hovertemplate: `<extra></extra>`,
            },
            figName: key + "Boxplot"
          });
        }
      }
    }

    setRenderData(graphSeries);
  }, [cacheData, centerFreq]);

  const refreshRender = (fig, figName) => {
    for (let i in renderData) {
      if (renderData[i].figName == figName) {
        if (renderData[i].type === "line") {
          fig.plot(renderData[i].x, renderData[i].y, renderData[i].options);
        } else if (renderData[i].type === "box") {
          fig.box(renderData[i].x, renderData[i].y, renderData[i].options);
          fig.setSubtitle("Spectral Features @ " + centerFreq.toFixed(1) + " Hz");
          fig.setXlabel(renderData[i].parameter, {fontSize: 15});
          fig.setYlim([0, math.max(renderData[i].y)*1.1]);
        }
      }
    }
    fig.render();
  }

  useEffect(() => {
    for (let key in figGroup) {
      const fig = figGroup[key];
      if (key.endsWith("Boxplot")) {
        fig.traces = [];
        refreshRender(fig, key);
      } else {
        fig.traces = [];
        refreshRender(fig, key);
      }
      
      const ref = document.getElementById(figureTitle + "_" + key);
      if (ref) {
        ref.on("plotly_click", plotly_onClick);
      };
      
      setRefresh((refresh) => {
        return refresh += 1;
      });
    }

    return () => {
      for (let key in figGroup) {
        const ref = document.getElementById(figureTitle + "_" + key);
        if (ref && ref.removeListener) {
          ref.removeListener("plotly_click", plotly_onClick);
        };
      }
    }
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
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <MDBox px={3} pt={3}>
          <Autocomplete
            value={parameter}
            options={["Amplitude", "Frequency", "Pulsewidth"]}
            onChange={(event, value) => setParameter(value)}
            renderInput={(params) => (
              <FormField
                {...params}
                label={"Therapy Label Selector"}
                InputLabelProps={{ shrink: true }}
              />
            )}
            disableClearable
          />
        </MDBox>
      </Grid>
      {dataToRender.AllChannels.map((a, thatIndex) => {
        let visibility = activeChannels.includes(a) && (figGroup[a] && figGroup[a].traces.length > 0);
        return [
          <Grid key={figureTitle + "_SwitchControl"} item xs={12}>
            <MDBox px={3}>
              <FormControlLabel control={<Switch value={therapyLabel[a] != a} onChange={(event, value) => {
                if (dataToRender.AllChannels.length == 2) {
                  setTherapyLabel({...therapyLabel, [a]: therapyLabel[a] == dataToRender.AllChannels[0] ? dataToRender.AllChannels[1] : dataToRender.AllChannels[0]})
                }
              }} />} label="Contralateral Stimulation Label" />
            </MDBox>
          </Grid>,
          <Grid key={figureTitle + "_" + a} item xs={12} sm={6}>
            <MDBox ref={ref} id={figureTitle + "_" + a} style={{height: 600, width: "100%", display: visibility ? "" : "none"}}/>
          </Grid>,
          <Grid key={figureTitle + "Boxplot_" + a} item xs={12} sm={6}>
            <MDBox id={figureTitle + "Boxplot_" + a} style={{height: 600, width: "100%", display: visibility ? "" : "none"}}/>
          </Grid>
        ]
      })}
    </Grid>
  ), [refresh]);
}

export default StimulationPSD;