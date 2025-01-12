/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useResizeDetector } from 'react-resize-detector';

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";

import { Menu, MenuItem, Dialog, DialogContent, Grid, Autocomplete, TextField, DialogActions } from "@mui/material";
import { createFilterOptions } from "@mui/material/Autocomplete";

import MedtronicCircadianRhythm from "./MedtronicCircadianRhythm";

export default function CircadianRhythm({data, activeChannel, annotations, showEventCount, ...rest}) {
  return useMemo(() => {
    if (data.AnalysisType === "MedtronicChronicBrainSense") {
      return <MedtronicCircadianRhythm dataToRender={data.ChronicNeuralActivity} activeChannel={activeChannel} annotations={annotations} showEventCount={showEventCount} {...rest} />
    }
  }, [data, annotations, activeChannel, showEventCount]);
};

