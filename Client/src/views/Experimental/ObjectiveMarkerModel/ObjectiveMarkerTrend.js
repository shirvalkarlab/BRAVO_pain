/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useCallback } from "react";
import { useResizeDetector } from 'react-resize-detector';

import MDBox from "components/MDBox";

import colormap from "colormap";

import { PlotlyRenderManager } from "graphing-utility/Plotly";

import { dictionary, dictionaryLookup } from "assets/translation";
import { usePlatformContext } from "context";

function ObjectiveMarkerTrend({dataToRender, objectiveMarker, height, figureTitle}) {
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;

  const [show, setShow] = React.useState(false);
  const fig = new PlotlyRenderManager(figureTitle, language);
  
  const handleGraphing = (data) => {
    fig.clearData();

    if (fig.fresh) {
      var ax = fig.subplots(2, 1, {sharex: true, sharey: true});
      fig.setXlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Time", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "Local", language)})`, {fontSize: 15}, ax[1]);
      fig.setYlabel(`${dictionaryLookup(dictionary.FigureStandardText, "Power", language)} (${dictionaryLookup(dictionary.FigureStandardUnit, "AU", language)})`, {fontSize: 15}, ax[0]);
      fig.setYlabel(`Probability of ${objectiveMarker.params.event}`, {fontSize: 15}, ax[1]);
      
      fig.setYlim([0, 100], ax[1]);

      /*
      if (data[i].Hemisphere === data[i].CustomName) {
        const [side, target] = data[i].Hemisphere.split(" ");
        const titleText = `${dictionaryLookup(dictionary.FigureStandardText, side, language)} ${dictionaryLookup(dictionary.BrainRegions, target, language)}`;
        fig.setSubtitle(`${titleText}`,ax[i*2]);
      } else {
        fig.setSubtitle(`${data[i].CustomName}`,ax[i*2]);
      }
        */
      
      //fig.setSubtitle(`${dictionaryLookup(dictionary.FigureStandardText, "Stimulation", language)}`,ax[i*2+1]);

      fig.setLegend({
        tracegroupgap: 5,
      });

      fig.setLayoutProps({
        hovermode: "x"
      });
    }

    for (let i in data) {
      if (data[i].Device == objectiveMarker.params.device && data[i].Hemisphere == objectiveMarker.params.target) {
        for (let j in data[i].Therapy) {
          if (data[i].Therapy[j].TherapyOverview == objectiveMarker.params.therapy) {
            var timeArray = Array(data[i]["Timestamp"][j].length).fill(0).map((value, index) => new Date(data[i]["Timestamp"][j][index]*1000));
            fig.plot(timeArray, data[i]["Power"][j], {
              linewidth: 1,
              color: "#000000",
              hovertemplate: "  %{x} <br>  " + objectiveMarker.params.therapy + "<br>  %{y:.2f} <extra></extra>"
            }, ax[0]);
          }
        }
      }
    }

    
    fig.bar(objectiveMarker.timestamp.map((a) => new Date(a*1000)), objectiveMarker.probability.map((a) => a*100), {
      color: "#FF0000",
      showlegend: false,
      hovertemplate: "  %{x}" + "<br>  %{y:.2f}% <extra></extra>"
    }, ax[1]);
    
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
    if (dataToRender && objectiveMarker.model) {
      handleGraphing(dataToRender);
    };
  }, [dataToRender, objectiveMarker, language]);

  const onResize = useCallback(() => {
    fig.refresh();
  }, []);

  const {ref} = useResizeDetector({
    onResize: onResize,
    refreshMode: "debounce",
    refreshRate: 50,
    skipOnMount: false
  });

  return (
    <MDBox ref={ref} id={figureTitle} style={{marginTop: 5, marginBottom: 10, height: height, width: "100%", display: show ? "" : "none"}}/>
  );
}

export default ObjectiveMarkerTrend;