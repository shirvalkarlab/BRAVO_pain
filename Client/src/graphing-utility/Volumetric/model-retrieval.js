/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { SessionController } from "database/session-control";
import { identityMatrix, computeElectrodePlacement, parseBinarySTL } from ".";
import * as THREE from "three";
import * as math from "mathjs";

/**
 * Wrapper for retriving models from UF BRAVO Platform Backend Server. 
 *
 * @param {string} directory - Directory that store the model. Typically the Patient ID.
 * @param {Object} item - The model object that describe the available models in the server. 
 * @param {string} color - Hex-encoded color string to force model into specific colors. 
 * 
 * @return {Object[]} Array of controllable items that contain both data and description of the model downloaded. 
 */
const retrieveModels = async (participant_uid, item, color) => {
  const controlledItems = [];
  
  if (item.DataType == "STL") {
    const response = await SessionController.query("/api/downloadData", {
      "ParticipantId": participant_uid,
      "CacheType": "queryImageModel",
      "DataId": item.Id,
      "FileType": item.DataType
    }, {}, null, "arraybuffer");
    const data = parseBinarySTL(response.data);
    controlledItems.push({
      id: item.Id,
      filename: item.Name,
      type: item.DataType,
      downloaded: true,
      data: data,
      opacity: 1,
      color: color ? color : data.color,
      matrix: identityMatrix(),
      show: true,
    });
  
  } else if (item.DataType == "Electrodes") {
    const response = await SessionController.query("/api/queryImageSourceFiles", {
      RequestType: "GetPagination",
      ParticipantId: participant_uid,
      SourceId: item.Id,
      ElectrodeName: item.Name
    });

    const targetPt = response.data[0].TargetPoint || [0,0,0];
    const entryPt = response.data[0].EntryPoint || [0,0,50];

    const electrode_data = {
      id: item.Id,
      filename: item.Name,
      type: item.DataType,
      downloaded: true,
      subname: [],
      data: [],
      color: color,
      opacity: 1,
      targetPt: targetPt,
      entryPt: entryPt,
      matrix: computeElectrodePlacement(targetPt, entryPt),
      show: true,
    };
    
    for (let segment of response.data) {
      const response = await SessionController.query("/api/downloadData", {
        "ParticipantId": participant_uid,
        "CacheType": "queryImageModel",
        "DataId": segment.SourceId,
        "RecordingId": segment.RecordingId
      }, {}, null, "arraybuffer");
      const data = parseBinarySTL(response.data);
      electrode_data.subname.push(segment.Name);
      electrode_data.data.push(data);
    }
    return [electrode_data]

  } else if (item.DataType == "TemplateElectrodes") {
    const response = await SessionController.query("/api/queryImageSourceFiles", {
      RequestType: "GetPagination",
      ParticipantId: participant_uid,
      SourceId: item.Id,
      ElectrodeName: item.Name
    });

    const targetPt = response.data[0].TargetPoint || [0,0,0];
    const entryPt = response.data[0].EntryPoint || [0,0,50];

    const electrode_data = {
      id: response.data[0].SourceId,
      filename: item.Name,
      type: "Electrodes",
      downloaded: true,
      subname: [],
      data: [],
      color: color,
      opacity: 1,
      targetPt: targetPt,
      entryPt: entryPt,
      matrix: computeElectrodePlacement(targetPt, entryPt),
      show: true,
    };
    
    for (let segment of response.data) {
      const response = await SessionController.query("/api/downloadData", {
        "ParticipantId": participant_uid,
        "CacheType": "queryImageModel",
        "DataId": segment.SourceId,
        "RecordingId": segment.RecordingId
      }, {}, null, "arraybuffer");
      const data = parseBinarySTL(response.data);
      electrode_data.subname.push(segment.Name);
      electrode_data.data.push(data);
    }
    return [electrode_data]

  } else if (item.DataType == "Blender Scene") {
    controlledItems.push({
      id: item.Id,
      filename: item.Name,
      type: item.DataType,
      downloaded: false,
      data: SessionController.getDownloadLink("/api/downloadData", {
        ParticipantId: participant_uid,
        CacheType: "queryImageModel",
        RecordingId: item.Id
      }),
      show: true,
    });

  } else if (item.type == "volume") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    }, {}, null, "arraybuffer");
    return response.data;

  } else if (item.type == "tracts") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    });
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: response.data.points,
      thickness: 1,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  } else if (item.type == "points") {
    const response = await SessionController.query("/api/queryImageModel", {
      "Directory": participant_uid,
      "FileName": item.file,
      "FileMode": item.mode,
      "FileType": item.type
    });
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: response.data.points,
      thickness: 1,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  } else if (item.type == "sphere") {
    controlledItems.push({
      filename: item.file,
      type: item.type,
      downloaded: true,
      data: item.targetPoints,
      color: color ? color : "#FFFFFF",
      matrix: identityMatrix(),
      show: true,
    });

  }
  return controlledItems;

};

export default retrieveModels; 