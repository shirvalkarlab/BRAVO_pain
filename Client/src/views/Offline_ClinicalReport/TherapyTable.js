/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import {
  Box,
  Backdrop,
  Badge,
  IconButton,
  Dialog,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Card,
  Grid,
  Table,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
  ToggleButtonGroup,
  ToggleButton,
  Tooltip,
} from "@mui/material"

import {v4 as uuid4} from "uuid";

// core components
import MDTypography from "components/MDTypography";
import MDBox from "components/MDBox";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import LoadingProgress from "components/LoadingProgress";

import TherapyModificationHistory from "views/Reports/TherapyHistory/TherapyModificationHistory";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";

function TherapyTable({JSONData, onUpdateTherapyConfigurations}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language, report } = controller;

  const [therapyTimeline, setTherapyTimeline] = React.useState([]);
  const [therapyDevice, setTherapyDevice] = React.useState({});

  const getTherapyDevice = (JSONData) => {
    let device = {
      Id: JSONData.DeviceInformation.Final.NeurostimulatorSerialNumber || "Unknown Device",
      Date: JSONData.DeviceInformation.Final.ImplantDate ? new Date(JSONData.DeviceInformation.Final.ImplantDate).getTime() / 1000 : 0,
    }
    return device;
  };

  const getElectrodes = (JSONData) => {
    // Build and return an array of electrode objects derived from JSONData
    const electrodes = [];
    const leadInfo = JSONData?.LeadConfiguration?.Final || [];

    for (const lead of leadInfo) {
      // Build TargetLocation (e.g. "Left STN")
      let targetLocation = (lead.Hemisphere || "").replace("HemisphereLocationDef.", "") + " ";
      const loc = lead.LeadLocation || "";
      if (loc === "LeadLocationDef.Vim") targetLocation += "VIM";
      else if (loc === "LeadLocationDef.Stn") targetLocation += "STN";
      else if (loc === "LeadLocationDef.Gpi") targetLocation += "GPi";
      else targetLocation += loc.replace("LeadLocationDef.", "");

      const electrode = {
        name: targetLocation,
        custom_name: targetLocation,
        hemisphere: targetLocation.split(" ")[0],
        target: targetLocation.split(" ")[1],
      };

      // Channel count based on ElectrodeNumber
      const num = lead.ElectrodeNumber;
      if (num === "InsPort.ZERO_THREE" || num === "InsPort.EIGHT_ELEVEN") electrode.channel_count = 4;
      else if (num === "InsPort.ZERO_SEVEN" || num === "InsPort.EIGHT_FIFTEEN") electrode.channel_count = 8;

      // Model-specific channel names and types
      const model = lead.Model;
      if (model === "LeadModelDef.LEAD_B33015") {
        electrode.type = "SenSight B33015";
        electrode.channel_names = ["E00","E01-A","E01-B","E01-C","E02-A","E02-B","E02-C","E03"];
      } else if (model === "LeadModelDef.LEAD_B33005") {
        electrode.type = "SenSight B33005";
        electrode.channel_names = ["E00","E01-A","E01-B","E01-C","E02-A","E02-B","E02-C","E03"];
      } else if (model === "LeadModelDef.LEAD_3387") {
        electrode.type = "Medtronic 3387";
        electrode.channel_names = ["E00","E01","E02","E03"];
        electrode.channel_count = electrode.channel_count || 4;
      } else if (model === "LeadModelDef.LEAD_3389") {
        electrode.type = "Medtronic 3389";
        electrode.channel_names = ["E00","E01","E02","E03"];
        electrode.channel_count = electrode.channel_count || 4;
      } else if (model === "LeadModelDef.LEAD_OTHER") {
        electrode.type = "Other";
        const cc = electrode.channel_count || 0;
        electrode.channel_names = Array.from({ length: cc }, (_, i) => `Contact-${i}`);
      } else {
        // Default: strip prefix and build contact names
        electrode.type = (model || "").replace("LeadModelDef.", "");
        const cc = electrode.channel_count || 0;
        electrode.channel_names = Array.from({ length: cc }, (_, i) => `Contact-${i}`);
      }

      electrodes.push(electrode);
    }

    let formattedElectrodes = electrodes.map((elec) => {
      return {
        Id: uuid4(),
        Name: elec.name,
        Type: elec.type,
        CustomName: elec.custom_name,
        Hemisphere: elec.hemisphere,
        Target: elec.target,
        Date: new Date().getTime()/1000,
        ChannelCount: elec.channel_count,
        ChannelNames: elec.channel_names,
      };
    });
    return formattedElectrodes;
  };

  const processTherapySettings = (TherapyGroup) =>{
    const Therapy = {};
    Therapy["GroupId"] = TherapyGroup.GroupId;
    Therapy["GroupName"] = TherapyGroup.GroupName || "";
    Therapy["ActiveGroup"] = TherapyGroup.ActiveGroup !== undefined ? TherapyGroup.ActiveGroup : false;

    if (!TherapyGroup.ProgramSettings) return Therapy;

    const ps = TherapyGroup.ProgramSettings;
    // Sensing channel based settings
    if (ps.SensingChannel && Array.isArray(ps.SensingChannel)) {
      for (let side = 0; side < ps.SensingChannel.length; side++) {
        const sc = ps.SensingChannel[side];
        const hemisphere = sc.HemisphereLocation === "HemisphereLocationDef.Left" ? "LeftHemisphere" : "RightHemisphere";

        Therapy[hemisphere] = {};
        Therapy[hemisphere]["Mode"] = "BrainSense";
        Therapy[hemisphere]["Frequency"] = ps.RateInHertz !== undefined ? ps.RateInHertz : sc.RateInHertz;
        Therapy[hemisphere]["PulseWidth"] = sc.PulseWidthInMicroSecond;
        Therapy[hemisphere]["Unit"] = "mA";
        Therapy[hemisphere]["Amplitude"] = sc.SuspendAmplitudeInMilliAmps;
        Therapy[hemisphere]["Channel"] = sc.ElectrodeState;
        Therapy[hemisphere]["LFPThresholds"] = [sc.LowerLfpThreshold, sc.UpperLfpThreshold];
        Therapy[hemisphere]["CaptureAmplitudes"] = [sc.LowerCaptureAmplitudeInMilliAmps, sc.UpperCaptureAmplitudeInMilliAmps];
        Therapy[hemisphere]["MeasuredLFP"] = [sc.MeasuredLowerLfp, sc.MeasuredUpperLfp];

        if (TherapyGroup.Mode) {
          if (TherapyGroup.Mode === "LimitModeDef.AdvanceEdit" && sc.LowerLimitInMilliAmps !== undefined) {
            Therapy[hemisphere]["AmplitudeThreshold"] = [sc.LowerLimitInMilliAmps, sc.UpperLimitInMilliAmps];
          } else if (ps[hemisphere] && TherapyGroup.Mode === "LimitModeDef.AdvanceEdit" && ps[hemisphere].LowerLimitInMilliAmps !== undefined) {
            Therapy[hemisphere]["AmplitudeThreshold"] = [ps[hemisphere].LowerLimitInMilliAmps, ps[hemisphere].UpperLimitInMilliAmps];
          }
        } else {
          Therapy[hemisphere]["AmplitudeThreshold"] = [0, 0];
        }

        Therapy[hemisphere]["SensingSetup"] = sc.SensingSetup ? { ...sc.SensingSetup } : {};
        if (Therapy[hemisphere]["SensingSetup"] && Therapy[hemisphere]["SensingSetup"].ChannelSignalResult) {
          delete Therapy[hemisphere]["SensingSetup"].ChannelSignalResult;
        }

        if (sc.AdaptiveTherapy) {
          Therapy[hemisphere]["AdaptiveSetup"] = { ...sc.AdaptiveTherapy };
          Therapy[hemisphere]["AdaptiveSetup"]["Status"] = sc.AdaptiveTherapyStatus;
          if (Therapy[hemisphere]["AdaptiveSetup"]["Status"] !== "ADBSStatusDef.NOT_CONFIGURED") {
            Therapy[hemisphere]["AdaptiveSetup"]["Mode"] = sc.Mode;
            Therapy[hemisphere]["AdaptiveSetup"]["RampUpTime"] = sc.TransitionUpInMilliSeconds;
            Therapy[hemisphere]["AdaptiveSetup"]["RampDownTime"] = sc.TransitionDownInMilliSeconds;
            if (sc.GangedToHemisphere !== undefined) Therapy[hemisphere]["AdaptiveSetup"]["Bypass"] = sc.GangedToHemisphere;
          }
        }

        Therapy[hemisphere]["SensingSetup"]["Status"] = sc.BrainSensingStatus;
      }
    }

    // Left hemisphere program settings (may overwrite sensing-based object)
    if (ps.LeftHemisphere) {
      Therapy["LeftHemisphere"] = {};
      const left = ps.LeftHemisphere;
      if (Array.isArray(left.Programs) && left.Programs.length > 1) {
        Therapy["LeftHemisphere"]["Mode"] = "Interleaving";
      } else {
        Therapy["LeftHemisphere"]["Mode"] = "Standard";
      }

      if (Therapy["LeftHemisphere"]["Mode"] === "Interleaving") {
        Therapy["LeftHemisphere"]["Frequency"] = ps.RateInHertz !== undefined ? [ps.RateInHertz, ps.RateInHertz] : [left.Programs[0].RateInHertz, left.Programs[1].RateInHertz];
        Therapy["LeftHemisphere"]["ProgramId"] = [];
        Therapy["LeftHemisphere"]["PulseWidth"] = [];
        Therapy["LeftHemisphere"]["Amplitude"] = [];
        Therapy["LeftHemisphere"]["Channel"] = [];
        Therapy["LeftHemisphere"]["Unit"] = [];
        for (let i = 0; i < left.Programs.length; i++) {
          const p = left.Programs[i];
          Therapy["LeftHemisphere"]["ProgramId"].push(p.ProgramId);
          Therapy["LeftHemisphere"]["PulseWidth"].push(p.PulseWidthInMicroSecond);
          if (p.AmplitudeInMilliAmps !== undefined) {
            Therapy["LeftHemisphere"]["Amplitude"].push(p.AmplitudeInMilliAmps);
            Therapy["LeftHemisphere"]["Unit"].push("mA");
          } else if (p.AmplitudeInVolts !== undefined) {
            Therapy["LeftHemisphere"]["Amplitude"].push(p.AmplitudeInVolts);
            Therapy["LeftHemisphere"]["Unit"].push("V");
          }
          Therapy["LeftHemisphere"]["Channel"].push(p.ElectrodeState);
        }
      } else {
        Therapy["LeftHemisphere"]["Frequency"] = ps.RateInHertz !== undefined ? ps.RateInHertz : left.Programs[0].RateInHertz;
        Therapy["LeftHemisphere"]["PulseWidth"] = left.Programs[0].PulseWidthInMicroSecond;
        if (left.Programs[0].AmplitudeInMilliAmps !== undefined) {
          Therapy["LeftHemisphere"]["Amplitude"] = left.Programs[0].AmplitudeInMilliAmps;
          Therapy["LeftHemisphere"]["Unit"] = "mA";
        } else if (left.Programs[0].AmplitudeInVolts !== undefined) {
          Therapy["LeftHemisphere"]["Amplitude"] = left.Programs[0].AmplitudeInVolts;
          Therapy["LeftHemisphere"]["Unit"] = "V";
        }
        Therapy["LeftHemisphere"]["Channel"] = left.Programs[0].ElectrodeState;
      }
    }

    // Right hemisphere program settings
    if (ps.RightHemisphere) {
      Therapy["RightHemisphere"] = {};
      const right = ps.RightHemisphere;
      if (Array.isArray(right.Programs) && right.Programs.length > 1) {
        Therapy["RightHemisphere"]["Mode"] = "Interleaving";
      } else {
        Therapy["RightHemisphere"]["Mode"] = "Standard";
      }

      if (Therapy["RightHemisphere"]["Mode"] === "Interleaving") {
        Therapy["RightHemisphere"]["Frequency"] = ps.RateInHertz !== undefined ? [ps.RateInHertz, ps.RateInHertz] : [right.Programs[0].RateInHertz, right.Programs[1].RateInHertz];
        Therapy["RightHemisphere"]["ProgramId"] = [];
        Therapy["RightHemisphere"]["PulseWidth"] = [];
        Therapy["RightHemisphere"]["Amplitude"] = [];
        Therapy["RightHemisphere"]["Channel"] = [];
        Therapy["RightHemisphere"]["Unit"] = [];
        for (let i = 0; i < right.Programs.length; i++) {
          const p = right.Programs[i];
          Therapy["RightHemisphere"]["ProgramId"].push(p.ProgramId);
          Therapy["RightHemisphere"]["PulseWidth"].push(p.PulseWidthInMicroSecond);
          if (p.AmplitudeInMilliAmps !== undefined) {
            Therapy["RightHemisphere"]["Amplitude"].push(p.AmplitudeInMilliAmps);
            Therapy["RightHemisphere"]["Unit"].push("mA");
          } else if (p.AmplitudeInVolts !== undefined) {
            Therapy["RightHemisphere"]["Amplitude"].push(p.AmplitudeInVolts);
            Therapy["RightHemisphere"]["Unit"].push("V");
          }
          Therapy["RightHemisphere"]["Channel"].push(p.ElectrodeState);
        }
      } else {
        Therapy["RightHemisphere"]["Frequency"] = ps.RateInHertz !== undefined ? ps.RateInHertz : right.Programs[0].RateInHertz;
        Therapy["RightHemisphere"]["PulseWidth"] = right.Programs[0].PulseWidthInMicroSecond;
        if (right.Programs[0].AmplitudeInMilliAmps !== undefined) {
          Therapy["RightHemisphere"]["Amplitude"] = right.Programs[0].AmplitudeInMilliAmps;
          Therapy["RightHemisphere"]["Unit"] = "mA";
        } else if (right.Programs[0].AmplitudeInVolts !== undefined) {
          Therapy["RightHemisphere"]["Amplitude"] = right.Programs[0].AmplitudeInVolts;
          Therapy["RightHemisphere"]["Unit"] = "V";
        }
        Therapy["RightHemisphere"]["Channel"] = right.Programs[0].ElectrodeState;
      }
    }

    Therapy["GroupSettings"] = TherapyGroup.GroupSettings ? TherapyGroup.GroupSettings : {};

    return Therapy;
  }


  function reformatElectrodeDef(electrodeDef) {
    if (typeof electrodeDef !== 'string') throw new Error('Incorrect Electrode Definition String.');
    const ed = electrodeDef.toUpperCase();
    if (!ed.startsWith('ELECTRODEDEF.')) throw new Error('Incorrect Electrode Definition String.');

    let channelName;
    let channelID;
    if (ed.indexOf('FOURELECTRODES') >= 0) {
      channelName = 'E' + ed.replace('ELECTRODEDEF.FOURELECTRODES_', '');
      channelID = parseInt(ed.replace('ELECTRODEDEF.FOURELECTRODES_', ''), 10);
    } else if (ed.indexOf('SENSIGHT') >= 0) {
      channelName = 'E' + ed.replace('ELECTRODEDEF.SENSIGHT_', '');
      const lastChar = channelName.charAt(channelName.length - 1);
      if (/\d/.test(lastChar)) {
        channelID = parseInt(channelName.slice(1), 10);
        if (channelID % 8 !== 0) channelID += 4;
      } else if (channelName.endsWith('A')) {
        const n = parseInt(channelName.slice(1, -1), 10);
        channelID = ((n % 8) - 1) * 3 + 1;
      } else if (channelName.endsWith('B')) {
        const n = parseInt(channelName.slice(1, -1), 10);
        channelID = ((n % 8) - 1) * 3 + 2;
      } else if (channelName.endsWith('C')) {
        const n = parseInt(channelName.slice(1, -1), 10);
        channelID = ((n % 8) - 1) * 3 + 3;
      } else {
        throw new Error('Unknown electrode format for SENSIGHT.');
      }
    } else if (ed.indexOf('CASE') >= 0) {
      channelName = 'CAN';
      channelID = -1;
    } else {
      throw new Error('Unknown Electrode Definition String.');
    }

    return { channelName, channelID };
  }

  const extractTherapySettings = (therapyList) => {
    const settings = [];
    for (let therapy of therapyList) {
      for (let hemisphere of ["LeftHemisphere", "RightHemisphere"]) {
        if (!therapy[hemisphere]) continue;

        const therapyObject = {
          hemisphere,
          group_name: therapy.GroupName,
          group_id: therapy.GroupId,
          group_type: "",
          stimulation_type: therapy[hemisphere].Mode,
          stimulation_settings: [],
          adaptive_settings: [],
          sensing_settings: []
        };

        if (therapyObject.stimulation_type === "Interleaving") {
          for (let i in therapy[hemisphere].Frequency) {
            let stimulationSetting = {
              amplitude: therapy[hemisphere].Amplitude[i],
              amplitude_unit: therapy[hemisphere].Unit[i],
              pulsewidth: therapy[hemisphere].PulseWidth[i],
              pulsewidth_unit: "uS",
              frequency: therapy[hemisphere].Frequency[i],
            };

            let contact = [], amplitude = [], return_contact = [];
            for (let chan of therapy[hemisphere].Channel[i]) {
              const reformat = reformatElectrodeDef(chan.Electrode);
              if (chan.ElectrodeStateResult == "ElectrodeStateDef.Positive") {
                return_contact.push(reformat.channelID);
              } else if (chan.ElectrodeStateResult == "ElectrodeStateDef.Negative") {
                contact.push(reformat.channelID);
                if (chan.ElectrodeAmplitudeInMilliAmps) {
                  amplitude.push(chan.ElectrodeAmplitudeInMilliAmps);
                } else {
                  amplitude.push(therapy[hemisphere].Amplitude[i]);
                }
              }
            }
            stimulationSetting.amplitude_fraction = amplitude;
            stimulationSetting.contact = contact;
            stimulationSetting.return_contact = return_contact;

            try {
              if (therapy.GroupSettings.Cycling) {
                if (therapy.GroupSettings.Cycling.Enabled) {
                  stimulationSetting.cycling_period = therapy.GroupSettings.Cycling.OnDurationInMilliSeconds + therapy.GroupSettings.Cycling.OffDurationInMilliSeconds;
                  stimulationSetting.cycling = therapy.GroupSettings.Cycling.OnDurationInMilliSeconds / stimulationSetting.cycling_period;
                } else {
                  stimulationSetting.cycling = 1;
                }
              }
            } catch (error) {
              console.error("Error extracting cycling settings:", error);
            }
            therapyObject.stimulation_settings.push(stimulationSetting);
            therapyObject.sensing_settings.push(null);
            therapyObject.adaptive_settings.push(null);
          }
        } else {
          let stimulationSetting = {
            amplitude: therapy[hemisphere].Amplitude,
            amplitude_unit: therapy[hemisphere].Unit,
            pulsewidth: therapy[hemisphere].PulseWidth,
            pulsewidth_unit: "uS",
            frequency: therapy[hemisphere].Frequency,
          };

          let contact = [], amplitude = [], return_contact = [];
          for (let chan of therapy[hemisphere].Channel) {
            const reformat = reformatElectrodeDef(chan.Electrode);
            if (chan.ElectrodeStateResult == "ElectrodeStateDef.Positive") {
              return_contact.push(reformat.channelID);
            } else if (chan.ElectrodeStateResult == "ElectrodeStateDef.Negative") {
              contact.push(reformat.channelID);
              if (chan.ElectrodeAmplitudeInMilliAmps) {
                amplitude.push(chan.ElectrodeAmplitudeInMilliAmps);
              } else {
                amplitude.push(therapy[hemisphere].Amplitude);
              }
            }
          }
          stimulationSetting.amplitude_fraction = amplitude;
          stimulationSetting.contact = contact;
          stimulationSetting.return_contact = return_contact;

          try {
            if (therapy.GroupSettings.Cycling) {
              if (therapy.GroupSettings.Cycling.Enabled) {
                stimulationSetting.cycling_period = therapy.GroupSettings.Cycling.OnDurationInMilliSeconds + therapy.GroupSettings.Cycling.OffDurationInMilliSeconds;
                stimulationSetting.cycling = therapy.GroupSettings.Cycling.OnDurationInMilliSeconds / stimulationSetting.cycling_period;
              } else {
                stimulationSetting.cycling = 1;
              }
            }
          } catch (error) {
            console.error("Error extracting cycling settings:", error);
          }
          therapyObject.stimulation_settings.push(stimulationSetting);
          
          if (therapy[hemisphere].SensingSetup) {
            therapyObject.sensing_settings.push({
              type: "Medtronic BrainSense",
              sensing: {
                Thresholds: {
                  LFPThresholds: therapy[hemisphere].LFPThresholds ? therapy[hemisphere].LFPThresholds : [0,0],
                  MeasuredLFP: therapy[hemisphere].MeasuredLFP ? therapy[hemisphere].MeasuredLFP : [0,0],
                  CaptureAmplitudes: therapy[hemisphere].CaptureAmplitudes ? therapy[hemisphere].CaptureAmplitudes : [0,0],
                  AmplitudeThreshold: therapy[hemisphere].AmplitudeThreshold ? therapy[hemisphere].AmplitudeThreshold : [0,0],
                },
                SensingSetup: therapy[hemisphere].SensingSetup
              }
            });
          } else {
            therapyObject.sensing_settings.push(null);
          }
          
          if (therapy[hemisphere].AdaptiveSetup) {
            therapyObject.adaptive_settings.push({
              type: "Medtronic Adaptive",
              adaptive: therapy[hemisphere].AdaptiveSetup
            });
          } else {
            therapyObject.adaptive_settings.push(null);
          }
        }

        // Minimal placeholder: more detailed extraction can be implemented later.
        settings.push(therapyObject);
      }
    }
    return settings;
  };

  const getSettingInfo = (setting, therapy_type, electrode) => {
    let info = {
      Id: uuid4(),
      SourceId: "MedtronicJSON",
      Name: "",
      Type: therapy_type,
      Date: new Date().getTime() / 1000,
      Label: "",
      Timezone: "",
      GroupId: setting.group_id,
      GroupName: setting.group_name,
      GroupType: setting.group_type,
      StimulationType: setting.stimulation_type,
      StimulationSetting: setting.stimulation_settings.map((a) => {
        let setting = {
          Electrode: electrode,
          Contact: a.contact,
          ReturnContact: a.return_contact,
          Amplitude: a.amplitude,
          FractionalAmplitude: a.amplitude_fraction,
          AmplitudeUnit: a.amplitude_unit,
          Pulsewidth: a.pulsewidth,
          PulsewidthUnit: a.pulsewidth_unit,
          Frequency: a.frequency,
          Cycling: a.cycling,
          CyclingPeriod: a.cycling_period
        }

        let ValidContactName = true;
        for (let i of setting.Contact) {
          if (i >= electrode["ChannelNames"].length) {
            ValidContactName = false;
          }
        }

        if (ValidContactName) {
          setting.Contact = setting.Contact.map((b,k) => {
            return electrode["ChannelNames"][b];
          });
        }

        ValidContactName = true;
        for (let i of setting.ReturnContact) {
          if (i >= electrode["ChannelNames"].length) {
            ValidContactName = false;
          }
        }

        if (ValidContactName) {
          setting.ReturnContact = setting.ReturnContact.map((i) => {
            return i >= 0 ? electrode["ChannelNames"][i] : "CAN";
          });
        }

        return setting;
      }),
      AdaptiveSettings: setting.adaptive_settings.map((a, i) => {
        return {
          "RecordingConfiguration": {
            Type: setting.sensing_settings[i] ? setting.sensing_settings[i].type : "Unknown",
            Config: setting.sensing_settings[i] ? setting.sensing_settings[i].sensing : {}
          },
          "StimulationConfiguration": a ? {
            Type: a.type,
            Config: a.adaptive
          } : { Type: "Unknown", Config: {} }
        }
      })
    }

    
    return info;
  }

  const getTherapyTimeline = (JSONData) => {
    if (!JSONData.Groups) return [];
    const device = getTherapyDevice(JSONData);
    const electrodes = getElectrodes(JSONData);

    let TherapyTimeline = [];
    let therapyConfigurations = [];

    let timeline = {Date: new Date().getTime() / 1000, Therapies: [], DefinedTherapies: []};
    const previsitTherapy = extractTherapySettings(JSONData.Groups.Initial.map((a) => processTherapySettings(a)));
    const postvisitTherapy = extractTherapySettings(JSONData.Groups.Final.map((a) => processTherapySettings(a)));
    
    for (let setting of previsitTherapy) {
      therapyConfigurations.push({
        ...getSettingInfo(setting, "Pre-visit Therapy", electrodes.filter((a) => setting.hemisphere.startsWith(a.Hemisphere))[0]),
        Device: device
      });
    }
    for (let setting of postvisitTherapy) {
      therapyConfigurations.push({
        ...getSettingInfo(setting, "Post-visit Therapy", electrodes.filter((a) => setting.hemisphere.startsWith(a.Hemisphere))[0]),
        Device: device
      });
    }

    const GroupIds = [];
    for (let therapy of timeline.Therapies) {
      if (!GroupIds.includes(therapy.GroupId)) {
        GroupIds.push(therapy.GroupId);
      }
    }

    for (let i in GroupIds) {
      const GroupConfiguration = {
        GroupId: GroupIds[i],
        GroupEntries: [],
        Processed: []
      }

      for (let therapyType of ["Pre-visit Therapy", "Post-visit Therapy"]) {
        const groupTherapies = timeline.Therapies.filter((a) => a.GroupId === GroupIds[i] && a.Type === therapyType);
        GroupConfiguration.GroupEntries.push(...groupTherapies);

        let definedTherapy = {
          Device: device,
          Name: "", Type: therapyType,
          Date: timeline.Therapies[i].Date, Timezone: "",
          GroupId: timeline.Therapies[i].GroupId, GroupName: timeline.Therapies[i].GroupName,
          GroupType: "", TherapyLabel: "", 
          Electrodes: [], Stimulation: [], Adaptive: [], TherapyIds: []
        };

        for (let electrode of electrodes) {
          definedTherapy.Electrodes.push(electrode);
          for (let j in groupTherapies) {
            if (groupTherapies[j].StimulationSetting[0].Electrode.Id === electrode.Id) {
              definedTherapy.Stimulation.push(groupTherapies[j].StimulationSetting);
              definedTherapy.TherapyIds.push(groupTherapies[j].Id);
            }
          }
        }
      }
    }

    return TherapyTimeline;
  }

  React.useEffect(() => {
    if (JSONData) {
      const device = getTherapyDevice(JSONData);
      setTherapyDevice(device);

      const therapyTimeline = getTherapyTimeline(JSONData);
      setTherapyTimeline(therapyTimeline);
    }
  }, [JSONData]);

  return useMemo(() => {
    if (therapyTimeline.length < 1) {
      return <LoadingProgress />;
    }

    return (
      <Card>
        <MDBox p={2}>
          <TherapyModificationHistory therapyHistoryRaw={{
            TherapyTimeline: therapyTimeline,
            TherapyDevices: [therapyDevice],
          }} device={therapyDevice} />
        </MDBox>
      </Card>
    )
  }, [therapyTimeline]);
}

export default TherapyTable;