/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useCallback, useMemo, useState } from "react";
import {impedanceLayout} from "./plotLayout";
import { useResizeDetector } from 'react-resize-detector';

import MDBox from "components/MDBox";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { usePlatformContext } from "context";
import { dictionary, dictionaryLookup } from "assets/translation";

function ImpedanceHeatmap({dataToRender, onContactSelect, logType, height, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [show, setShow] = React.useState(false);
  const fig = useMemo(()=>new PlotlyRenderManager(figureTitle, language),[figureTitle,language]);
  const [plotWidth,setPlotWidth] = useState(0);
  const geometry = impedanceLayout(plotWidth,height);

  const handleGraphing = (data) => {
    fig.clearData();
    [...fig.getColorAxis()].forEach(axis=>fig.setColorAxis(null,axis));

    fig.subplots(geometry.rows,geometry.columns,{...geometry.spacing});
    fig.setLayoutProps(geometry.layout);
    let ax = fig.getAxes();
    if (data.Recording[0].Metadata && data.Recording[0].Metadata.Left) {
      if (logType == "Bipolar") {
        let contactArrayY = Array(data.Recording[0].Metadata.Left[logType].length).fill(0).map((value, index) => index);
        let contactArrayX = Array(data.Recording[0].Metadata.Left[logType][0].length).fill(0).map((value, index) => index);
        fig.surf(contactArrayX, contactArrayY, data.Recording[0].Metadata.Left[logType], {
          hovertemplate: `  %{z:d} Impedance <extra></extra>`,
          zsmooth: false,
          coloraxis: fig.createColorAxis({
            colorscale: "Jet",
            colorbar: {y: 0.5, len: 1},
            clim: [0,6000*contactArrayY.length/4],
            showscale: false
          }),
        }, ax[0]);
        fig.setSubtitle(`Left Hemisphere<br>${logType} Impedance Map`, ax[0]);
        
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayX,
          ticktext: contactArrayX.length == 4 ? contactArrayX : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "x", ax[0]);
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayY,
          ticktext: contactArrayY.length == 4 ? contactArrayY : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "y", ax[0]);
      } else {
        let contactArrayY = Array(data.Recording[0].Metadata.Left[logType].length).fill(0).map((value, index) => index);
        let contactArrayX = Array(data.Recording[0].Metadata.Left[logType][0].length).fill(0).map((value, index) => index);
        fig.surf(contactArrayX, contactArrayY, data.Recording[0].Metadata.Left[logType].map((value) => [value]), {
          hovertemplate: `  %{z:d} Impedance <extra></extra>`,
          zsmooth: false,
          coloraxis: fig.createColorAxis({
            colorscale: "Jet",
            colorbar: {y: 0.5, len: 1},
            clim: [0,4000*contactArrayY.length/4],
            showscale: false
          }),
        }, ax[0]);
        fig.setSubtitle(`Left Hemisphere<br>${logType} Impedance Map`, ax[0]);
        
        
        fig.setAxisProps({
          ticks: "",
          showticklabels: false
        }, "x", ax[0]);
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayY,
          ticktext: contactArrayY.length == 4 ? contactArrayY : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "y", ax[0]);
      }
    }

    if (data.Recording[0].Metadata && data.Recording[0].Metadata.Right) {
      if (logType == "Bipolar") {
        let contactArrayY = Array(data.Recording[0].Metadata.Right[logType].length).fill(0).map((value, index) => index);
        let contactArrayX = Array(data.Recording[0].Metadata.Right[logType][0].length).fill(0).map((value, index) => index);
        fig.surf(contactArrayX, contactArrayY, data.Recording[0].Metadata.Right[logType], {
          hovertemplate: `  %{z:d} Impedance <extra></extra>`,
          zsmooth: false,
          coloraxis: fig.createColorAxis({
            colorscale: "Jet",
            colorbar: {y: 0.5, len: 1},
            clim: [0,6000*contactArrayY.length/4],
            showscale: false
          }),
        }, ax[1]);
        fig.setSubtitle(`Right Hemisphere<br>${logType} Impedance Map`, ax[1]);
        
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayX,
          ticktext: contactArrayX.length == 4 ? contactArrayX : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "x", ax[1]);
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayY,
          ticktext: contactArrayY.length == 4 ? contactArrayY : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "y", ax[1]);
      } else {
        let contactArrayY = Array(data.Recording[0].Metadata.Right[logType].length).fill(0).map((value, index) => index);
        let contactArrayX = Array(data.Recording[0].Metadata.Right[logType][0].length).fill(0).map((value, index) => index);
        fig.surf(contactArrayX, contactArrayY, data.Recording[0].Metadata.Right[logType].map((value) => [value]), {
          hovertemplate: `  %{z:d} Impedance <extra></extra>`,
          zsmooth: false,
          coloraxis: fig.createColorAxis({
            colorscale: "Jet",
            colorbar: {y: 0.5, len: 1},
            clim: [0,4000*contactArrayY.length/4],
            showscale: false
          }),
        }, ax[1]);
        fig.setSubtitle(`Right Hemisphere<br>${logType} Impedance Map`, ax[1]);

        fig.setAxisProps({
          ticks: "",
          showticklabels: false
        }, "x", ax[1]);
        fig.setAxisProps({
          tickmode: "array",
          tickvals: contactArrayY,
          ticktext: contactArrayY.length == 4 ? contactArrayY : ["0","1A","1B","1C","2A","2B","2C","3"],
          showticklabels: true
        }, "y", ax[1]);
      }
    }

    for(const axis of ax){
      fig.setAxisProps(geometry.ticks,"x",axis);
      fig.setAxisProps(geometry.ticks,"y",axis);
    }
    fig.setLayoutProps({annotations:fig.layout.annotations.map(annotation=>({...annotation,font:{size:14}}))});

    if (!data) {
      fig.purge();
      setShow(false);
    } else {
      fig.render();
      setShow(true);
    }
  }

  // Refresh Left Figure if Data Changed
  React.useEffect(() => {
    if (dataToRender.length > 0) handleGraphing(dataToRender[dataToRender.length-1]);
    else {
      fig.purge();
      setShow(false);
    }
  }, [dataToRender, logType, fig, plotWidth,height]);

  const onResize = useCallback((width) => {
    setPlotWidth(width || 0);
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
        onContactSelect(data["points"][0]);
        plotly_singleclicked = false;
      }, 300);
    }
  };

  React.useEffect(() => {
    const node=ref.current;
    if (node && node.on) {
      node.on("plotly_click", plotly_onClick);
      return ()=>{if(node.removeListener)node.removeListener("plotly_click",plotly_onClick);};
    }
  }, [ref, dataToRender,onContactSelect]);

  return (
    <MDBox style={{width: "100%", minWidth: 0, display: show ? "" : "none"}}>
      <MDBox ref={ref} id={figureTitle} style={{height: geometry.layout.height, width: "100%", minWidth: 0}}/>
    </MDBox>
  );
}

export default ImpedanceHeatmap;
