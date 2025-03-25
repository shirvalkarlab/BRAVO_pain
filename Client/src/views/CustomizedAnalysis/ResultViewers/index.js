/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DialogContent } from "@mui/material";
import MDBox from "components/MDBox";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

import TimeDomainFigure from "./TimeDomainFigure";
import SpectrumFigure from "./SpectrumFigure";
import DistributionFigure from "./DistributionFigure";

function ResultViewer({participant_uid, analysisId, onClose, node}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { patientID, language } = controller;

  const [alert, setAlert] = useState(null);
  const [result, setResult] = useState({Type: "Unknown", Signal: [], Spectrum: []});

  useEffect(() => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "AnalysisOutput",
      ParticipantId: participant_uid,
      AnalysisId: analysisId,
      ResultId: node.result
    }).then((response) => {
      console.log(response.data)
      setResult(response.data);
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [node]);

  return (
    <DialogContent>
      {alert}
      <MDBox px={2} pt={2}>
        {result.Type === "TimeSeries" ? (
          <TimeDomainFigure dataToRender={result} analysisId={analysisId} resultId={node.result} figureTitle={"TimeDomainFigure"} />
        ) : null}
        {result.Spectrum.length > 0 ? (
          <SpectrumFigure dataToRender={result} analysisId={analysisId} resultId={node.result} figureTitle={"SpectrumFigure"} />
        ) : null}
        {result.Type === "Distribution" ? (
          <DistributionFigure dataToRender={result} analysisId={analysisId} resultId={node.result} figureTitle={"DistributionFigure"} />
        ) : null}
      </MDBox>
      <MDBox p={2}>
        <MDButton color={"secondary"} 
          onClick={onClose}
        >
          Close
        </MDButton>
      </MDBox>
    </DialogContent>
  )
}

export default ResultViewer;
