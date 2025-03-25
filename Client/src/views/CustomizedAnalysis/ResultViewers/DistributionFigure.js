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

import { Menu, MenuItem, DialogContent, Autocomplete, TextField, Stack, Switch, Grid } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import * as Math from "mathjs"
import colormap from "colormap";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { SessionController } from "database/session-control";
import { dictionary, dictionaryLookup } from "assets/translation";

function DistributionFigure({dataToRender, analysisId, resultId, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [alert, setAlert] = useState(null);

  const [fig, setFig] = useState(null);
  const [cachedData, setCachedData] = useState([]);
  const [availableChannels, setAvailableChannels] = useState({active: "", options: []});
  const [distribution, setDistribution] = useState({labels: [], values: []});
  const [data, setData] = useState({});
  const [renderData, setRenderData] = useState([]);

  const [computeBinaryThreshold, setComputeBinaryThreshold] = useState(false);
  const [cdfClasses, setCDFClasses] = useState({
    class1: "", class2: "", options: []
  });
  
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
    setCachedData(dataToRender.ActiveChannel);
    setAvailableChannels({active: "", options: dataToRender.AllChannels});
  }, [dataToRender]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    fig.subplots(1, 1, {sharey: false, sharex: false});
    fig.setLayoutProps({
      hovermode: "xy"
    });

  }, [fig, availableChannels]);

  useEffect(() => {
    if (!cachedData.includes(availableChannels.active)) {
      SessionController.query("/api/queryCustomizedAnalysis", {
        RequestType: "AnalysisOutput",
        ParticipantId: participant_uid,
        AnalysisId: analysisId,
        ResultId: resultId,
        ActiveChannels: [availableChannels.active]
      }).then((response) => {
        setCachedData((cachedData) => [...cachedData, availableChannels.active]);
        setData((data) => {
          data.Signal.push(...response.data.Signal);
          return {...data};
        });
      }).catch((error) => {
        SessionController.displayError(error, setAlert);
      });
    }
  }, [availableChannels.active])

  useEffect(() => {
    if (!fig) return;

    let uniqueLabels = [];
    
    const colors = colormap({
      colormap: 'rainbow',
      nshades: uniqueLabels.length > 9 ? uniqueLabels.length : 9,
      format: 'hex',
      alpha: 1,
    });

    let xData = [], yData = [];
    for (let i in data.Signal) {
      if (availableChannels.active == data.Signal[i].SignalSeries.ChannelNames) {
        for (let j in data.Signal[i].SignalSeries.Epochs) {
          xData.push(...data.Signal[i].SignalSeries.Epochs[j].Data.map((a) => data.Signal[i].SignalSeries.Epochs[j].Label));
          yData.push(...data.Signal[i].SignalSeries.Epochs[j].Data);
          if (!uniqueLabels.includes(data.Signal[i].SignalSeries.Epochs[j].Label)) uniqueLabels.push(data.Signal[i].SignalSeries.Epochs[j].Label);
          if (!uniqueLabels.includes(data.Signal[i].SignalSeries.Epochs[j].Label)) uniqueLabels.push(data.Signal[i].SignalSeries.Epochs[j].Label);
        }
      }
    }
    setDistribution({labels: xData, values: yData});
    setCDFClasses({...cdfClasses, options: uniqueLabels});
  }, [availableChannels.active, data]);

  useEffect(() => {
    let graphSeries = [];
    if (!computeBinaryThreshold) {
      graphSeries.push({
        type: "box",
        x: distribution.labels, y: distribution.values, 
        options: {
          width: 0.2,
          hovertemplate: `<extra></extra>`,
        },
      });
    } else {
      if (distribution.values.length > 0) {
        
        const ROC = distribution.values.map((a,i) => {
          return {label: distribution.labels[i], value: a};
        }).filter((a) => cdfClasses.class1 == a.label || cdfClasses.class2 == a.label).sort((a,b) => a.value - b.value);

        let class1 = 0, class2 = 0;
        const totalClass1 = ROC.reduce((acc, a) => {
          if (a.label == cdfClasses.class1) acc += 1;
          return acc;
        }, 0);
        const totalClass2 = ROC.reduce((acc, a) => {
          if (a.label == cdfClasses.class2) acc += 1;
          return acc;
        }, 0);
        let rates = [];
        let thresholds = [];
        
        for (let i in ROC) {
          thresholds.push(ROC[i].value);
          rates.push({
            fpr: ROC.reduce((acc, a) => {
              if (a.value >= ROC[i].value && a.label == cdfClasses.class2) acc += 1;
              return acc;
            }, 0) / totalClass2,
            tpr: ROC.reduce((acc, a) => {
              if (a.value >= ROC[i].value && a.label == cdfClasses.class1) acc += 1;
              return acc;
            }, 0) / totalClass1
          });
        }
        rates.push({fpr: 0, tpr: 0});
        
        graphSeries.push({
          type: "line",
          x: rates.map((a) => a.fpr), y: rates.map((a) => a.tpr),
          options: {
            linewidth: 2,
            meta: thresholds,
            color: "#FF0000",
            hovertemplate: "  Threshold: %{meta} <extra></extra>",
          },
        });
      }
    }
    setRenderData(graphSeries);
  }, [distribution, cdfClasses])

  const refreshRender = () => {
    fig.traces = [];
    for (let i in renderData) {
      if (renderData[i].type === "box") {
        fig.box(renderData[i].x, renderData[i].y, renderData[i].options);
        if (renderData[i].y.length > 0) fig.setYlim([0, Math.max(renderData[i].y)*1.1]);
        fig.setAxisProps({
          type: "category"
        }, "x");
        fig.setXlabel(``, {fontSize: 15});
        fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)}`, {fontSize: 15});
      } else if (renderData[i].type === "line") {
        fig.plot(renderData[i].x, renderData[i].y, renderData[i].options);
        fig.setXlim([0,1]);
        fig.setYlim([0,1]);
        fig.setAxisProps({
          type: "linear"
        }, "x");
        fig.setXlabel(`False Positive Rate`, {fontSize: 15});
        fig.setYlabel(`True Positive Rate`, {fontSize: 15});
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
      
      <MDBox py={2} lineHeight={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch value={computeBinaryThreshold} onClick={() => setComputeBinaryThreshold(!computeBinaryThreshold)} />
          <MDTypography variant={"subtitle"} fontSize={15}>
            {"Show Receiver-Operation Characteristic Curve"}
          </MDTypography>
        </Stack>
      </MDBox>

      {computeBinaryThreshold ? (
        <Grid container>
          <Grid item xs={4}>
            <Autocomplete selectOnFocus clearOnBlur fullWidth
              renderInput={(params) => (
                <TextField {...params} variant="standard" label={"Label 1"}/>
              )}
              isOptionEqualToValue={(option, value) => {
                return option === value;
              }}
              renderOption={(props, option) => <li {...props}>{option}</li>}
              value={cdfClasses.class1}
              options={cdfClasses.options}
              onChange={(event, newValue) => {
                setCDFClasses({...cdfClasses, class1: newValue});
              }}
            />
          </Grid>
          <Grid item xs={4}>

          </Grid>
          <Grid item xs={4}>
            <Autocomplete selectOnFocus clearOnBlur fullWidth
              renderInput={(params) => (
                <TextField {...params} variant="standard" label={"Label 2"}/>
              )}
              isOptionEqualToValue={(option, value) => {
                return option === value;
              }}
              renderOption={(props, option) => <li {...props}>{option}</li>}
              value={cdfClasses.class2}
              options={cdfClasses.options}
              onChange={(event, newValue) => {
                setCDFClasses({...cdfClasses, class2: newValue});
              }}
            />
          </Grid>
        </Grid>
      ) : null}

      <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 600, width: "100%", display: ""}}
        onContextMenu={onContextMenu}
      />
    </MDBox>
  );
}

export default DistributionFigure;