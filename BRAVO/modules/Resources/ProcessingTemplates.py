
ProcessingNodes = [{
    "Group": "Processing Template",
    "Type": "Default Timeseries Preprocessing",
    "Description": "",
    "NodeType": "SingleInputProcessingNode",
    "Configurations": [
        {
            "Id": "Butterworth Digital Filter",
            "Configurations": [
                {
                    "Id": "FilterType",
                    "Value": "Bandpass Filter"
                },
                {
                    "Id": "FilterRangeLow",
                    "Value": "1",
                },
                {
                    "Id": "FilterRangeHigh",
                    "Value": "100",
                }
            ],
        },
        {
            "Id": "Butterworth Digital Filter",
            "Configurations": [
                {
                    "Id": "FilterType",
                    "Value": "Bandstop Filter"
                },
                {
                    "Id": "FilterRangeLow",
                    "Value": "55",
                },
                {
                    "Id": "FilterRangeHigh",
                    "Value": "65",
                }
            ],
        }
    ]
},{
    "Group": "Processing Template",
    "Type": "Compare Power Band Distribution",
    "Description": "",
    "NodeType": "SingleInputProcessingNode",
    "Configurations": [
        {
            "Id": "Epoch by Annotations",
            "Configurations": [],
        },
        {
            "Id": "Compute Distribution",
            "Configurations": [],
        }
    ]
}]