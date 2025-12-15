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
import FormField from "components/MDInput/FormField";
import MDButton from "components/MDButton";
import { Autocomplete, Dialog, DialogContent, TextField, DialogActions, Grid, Menu, MenuItem } from "@mui/material";
import { createFilterOptions } from "@mui/material/Autocomplete";

import { AdapterMoment } from '@mui/x-date-pickers/AdapterMoment';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';

import * as math from "mathjs"
import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

const filter = createFilterOptions();

function CircadianDataDistribution({data, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [fig, setFig] = useState(null);
  const [renderData, setRenderData] = useState(null);
  const [timerange, setTimerange] = useState({device: "", start: null, end: null});

  useEffect(() => {
    const fig = new PlotlyRenderManager(figureTitle, language);
    setFig(fig);
  }, [figureTitle]);

  useEffect(() => {
    if (!fig) return;
    
    if (!fig.fresh) {
      fig.clearData();
    }

    let ax = fig.subplots(1, 1, {sharex: true, sharey: true});
    fig.setYlabel(`Probability`, {fontSize: 15}, ax[0]);

    if (!fig.fresh) {
      refreshRender();
    }
  }, [fig]);

  useEffect(() => {
    if (!fig || data.length == 0) return;

    const graphSeries = [{
      type: "histogram", x: data, options: {
        opacity: 1,
        xbins: {
          size: 10,
        },
        histnorm: "probability",
        facecolor: "#000000",
        hovertemplate: `  %{x} ${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)}<extra></extra>`,
        showlegend: false,
      }
    }];

    graphSeries.push({
      type: "line", x: math.quantileSeq(data, 0.25), tile: 25, options: {
        line: {color: "blue", width: 2, dash: "dash"},
        showlegend: false,
      }
    });
    graphSeries.push({
      type: "line", x: math.quantileSeq(data, 0.75), tile: 75, options: {
        line: {color: "red", width: 2, dash: "dash"},
        showlegend: false,
      }
    });

    setRenderData(graphSeries);
  }, [fig, data, timerange]);

  const refreshRender = () => {
    const layoutProps = {shapes: [], annotations: []};
    for (let i in renderData) {
      if (renderData[i].type == "histogram") {
        fig.hist(renderData[i].x, renderData[i].options);
        fig.setXlabel(`Power`, {fontSize: 15});
        fig.setYlabel(`Probability`, {fontSize: 15});
      } else if (renderData[i].type == "line") {
        layoutProps.shapes.push({
          type: 'line',
          x0: renderData[i].x, x1: renderData[i].x,
          y0: 0, y1: 1,
          xref: 'x', yref: 'paper',
          line: renderData[i].options.line
        });
        layoutProps.annotations.push({
          x: renderData[i].x, y: 1.02,
          xref: 'x', yref: 'paper',
          text: renderData[i].tile.toFixed(1) + "%: " + renderData[i].x.toFixed(0),
          showarrow: true, arrowhead: 3,
          ax: 0, ay: -renderData[i].tile,
          bgcolor: 'rgba(255,255,255,0.9)',
          bordercolor: renderData[i].options.line.color,
          borderwidth: 1,
          font: { color: renderData[i].options.line.color, size: 12 },
          align: 'center'
        });
      }
    }
    fig.setLayoutProps(layoutProps);
    fig.render();
  }

  useEffect(() => {
    if (!fig || !renderData) return;
    
    fig.traces = [];
    refreshRender();
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

  return useMemo(() => (
    <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: 600, width: "100%", display: ""}}/>
  ), [renderData, ref]);
}

export default CircadianDataDistribution;