<script>
import { mapState, mapActions, mapMutations } from 'vuex';
import djangoRest from '@/django';
import JsonDataTable from '../components/JsonDataTable';
import vegaEmbed from 'vega-embed';
import { csvParse } from 'd3-dsv';


export default {
  name: 'AnalysisView',
  components: {
    JsonDataTable,
  },
  inject: ['user'],
  data: () => ({
  }),
  computed: {
    ...mapState(['currentProject', 'allUsers', 'scans', 'selectedScan']),
    ScanName () {
      return this.scans[this.selectedScan].name;
    },
    permissions() {
      return this.currentProject.settings.permissions;
    },
    myod1Table() {
      let myod1_record = this.scans[this.selectedScan].analysis.filter(a => a.analysis_type === 'MYOD1');
      if (!myod1_record.length) {
        return [];
      }
      let myod1_stats = JSON.parse(myod1_record[0].analysis_result);

      let data = [myod1_stats]
      data.columns = ['Positive Score']
      let table = data
      // render by updating the this.table model
      djangoRest.getCohort('MYOD1').then((res) => {
        var vegaLiteSpec = {
          "title": "MYOD1 Mutation of Uploaded Image Compared to Our Cohort",
          "height":250,
          "width": 500,
          "data": {
            "values": res
          },
          "layer": [
            {
              "mark": "boxplot",
              "encoding": {
                "x": {
                  "field": "Positive Score",
                  "type": "quantitative",
                  "scale": {"zero": true}
                },
                "y": {
                  "field": "Category",
                  "type": "nominal"
                },
                "size": {"value":40},
                "color": {
                  "field": "Category",
                  "type":"nominal",
                  "scale": {"domain":["MYOD1-","MYOD1+","Uploaded Image"],"range": ["blue","red","orange"]}
                }
              }
            }, 
            {
              "mark": "rule",
              "data": {
                "values": [
                  {"Category": "Uploaded Image", "Positive Score": myod1_stats['Positive Score']}
                ]
              },
              "encoding": {
                "x": {
                  "field": "Positive Score",
                  "type": "quantitative"
                },
                "color": {"value": "orange"},
                "size": {"value": 4}
              }
            },
            {
              "mark": {
                  "type":"text",
                  "fontSize": 14,
                  "dx": 65
                  },
              "data": {
                "values": [
                  {"Category": "Uploaded Image", "Positive Score": myod1_stats['Positive Score']}
                ]
              },
              "encoding": {
                "text": {"field":"Positive Score","type":"quantitative"},
                "x": {
                  "field": "Positive Score",
                  "type": "quantitative"
                },
                "y": {
                    "field": "Category",
                    "type": "ordinal"
                    },
                "color": {"value": "orange"}
              }
            }
          ]
        };
        vegaEmbed(this.$refs.myod1VisModel, vegaLiteSpec,
                  {padding: 10, actions: {export: true, source: false, editor: false, compiled: false}});
      });
      return table;
    },
    survivabilityTable() {
      let survivability_record = this.scans[this.selectedScan].analysis.filter(a => a.analysis_type === 'SURVIVABILITY')
      if (!survivability_record.length || survivability_record[0].status === 2) {
        return []
      }
      let survivability_stats = JSON.parse(survivability_record[0].analysis_result);

      let secondBest = survivability_stats.secondBest
      // let data = [myod1_stats];
      // data.columns = ['Positive Score'];
      // let table = data;

      djangoRest.getCohort('SURVIVABILITY').then((res) => {
        for (let index = 0; index < res.length; index++) {
          var element = res[index];
          element['Hazard Prediction'] = parseFloat(element['Hazard Prediction'])
          res[index] = element
        }
        var vegaLiteSpec = {
            "title": "Predicted Survivability of the Uploaded Image Compared to Our Cohort",
            "height":250,
            "width": 500,
            "data": {
              "values": res
            },
            "layer": [
            {
              "mark": "boxplot",
              "encoding": {
                "x": {
                  "field": "Hazard Prediction",
                  "type": "quantitative",
                  "scale": {"zero": true}
                },
                "y": {
                  "field": "Risk Group",
                  "type": "nominal"
                },
                "size": {"value":40},
                "color": {
                  "field": "Risk Group",
                  "type":"nominal",
                  "scale": {"domain":["High","Intermediate","Low","Uploaded"],"range": ["red","green","blue","orange"]}
                }
                }
              }, 
              {
                  "mark": "rule",
                  "data": {
                    "values": [
                      {"Risk Group": "Uploaded", "Hazard Prediction": secondBest,  "Event Free Survival":"50"}
                    ]
                  },
                  "encoding": {
                    "x": {
                      "field": "Hazard Prediction",
                      "type": "quantitative"
                    },
                    "color": {"value": "orange"},
                    "size": {"value": 4}
                  }
                },
                {
                  "mark": {
                      "type":"text",
                      "fontSize": 14,
                      "dx": -25
                      },
                  "data": {
                    "values": [
                      {"Risk Group": "Uploaded", "Hazard Prediction": secondBest, "Event Free Survival":"50"}
                    ]
                  },
                  "encoding": {
                    "text": {"field":"Hazard Prediction","type":"quantitative"},
                    "x": {
                      "field": "Hazard Prediction",
                      "type": "quantitative"
                    },
                    "y": {
                        "field": "Risk Group",
                        "type": "ordinal"
                        },
                    "color": {"value": "orange"}
                  }
                }
            ]
        };
        vegaEmbed(this.$refs.survivabilityVisModel, vegaLiteSpec,
                  {padding: 10, actions: {export: true, source: false, editor: false, compiled: false}});
      })
      return survivability_stats
    }
  },
  watch: {
    currentProject(newProj) {
      this.selectedPermissionSet = { ...newProj.settings.permissions };
      this.emailList = this.currentProject.settings.default_email_recipients;
    },
  },
  methods: {
    ...mapActions(['loadAllUsers']),
    ...mapMutations(['setCurrentProject']),
    getGroup(user) {
      return Object.entries(this.permissions).filter(
        ([, value]) => value.includes(user),
      )[0][0].replace(/_/g, ' ');
    },
    userDisplayName(user) {
      if (!user.first_name || !user.last_name) {
        return user.username;
      }
      return `${user.first_name} ${user.last_name}`;
    },
    allEmails(inputs) {
      for (let i = 0; i < inputs.length; i += 1) {
        const match = String(inputs[i])
          .toLowerCase()
          .match(
            /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/,
          );
        if (!(match && match.length > 0)) return `${inputs[i]} is not a valid email address.`;
      }
      return true;
    },
    async savePermissions() {
      const newSettings = { ...this.currentProject.settings };
      newSettings.permissions = Object.fromEntries(
        Object.entries(this.selectedPermissionSet).map(
          ([group, list]) => [group, list.map((user) => user.username || user)],
        ),
      );
      try {
        const resp = await djangoRest.setProjectSettings(this.currentProject.id, newSettings);
        this.showAddMemberOverlay = false;
        this.showAddCollaboratorOverlay = false;
        const changedProject = { ...this.currentProject };
        changedProject.settings.permissions = resp.permissions;
        this.setCurrentProject(changedProject);
      } catch (e) {
        this.$snackbar({
          text: 'Failed to save permissions.',
          timeout: 6000,
        });
      }
    },
    async saveEmails() {
      const newSettings = { ...this.currentProject.settings };
      newSettings.default_email_recipients = this.emailList;
      delete newSettings.permissions;
      try {
        const resp = await djangoRest.setProjectSettings(this.currentProject.id, newSettings);
        const changedProject = { ...this.currentProject };
        changedProject.settings.default_email_recipients = resp.default_email_recipients;
        this.setCurrentProject(changedProject);
      } catch (e) {
        this.$snackbar({
          text: 'Failed to save email list.',
          timeout: 6000,
        });
      }
    },
  },
};
</script>

<template>
  <v-card class="flex-card">
    <v-subheader><b>{{ScanName}}</b>: Results</v-subheader>
    <v-container class="pl-2 pr-2">
      <div  align="center" justify="center" class="mt-20 mb-4 ml-4 mr-4">
        <div id="visM" ref="myod1VisModel" class="mt-20 mb-4 ml-4 mr-4"></div>
      </div>
      <div v-if="myod1Table.length > 0" class="mt-8 mb-4 ml-4 mr-4">
        <v-card-text>AI Predicted Score for MYOD1+ Mutation:</v-card-text>
        <json-data-table :data="myod1Table" />
      </div>
      <div  align="center" justify="center" class="mt-20 mb-4 ml-4 mr-4">
        <div id="visS" ref="survivabilityVisModel" class="mt-20 mb-4 ml-4 mr-4"></div>
      </div>
      <div v-if="survivabilityTable.length > 0" class="mt-8 mb-4 ml-4 mr-4">
        <v-card-text>Probability (0 to 1) of MYOD1+ Mutation:</v-card-text>
        <json-data-table :data="survivabilityTable" />
      </div>
    </v-container>
  </v-card>
</template>

<style lang="scss" scoped>
.gray-info {
  color: gray;
  padding-left: 10px;
  text-transform: capitalize;
}
.dialog-box {
  width: 40vw;
  min-height: 20vw;
  padding: 20px;
  background-color: white!important;
  color: '#333333'!important;
}
</style>
