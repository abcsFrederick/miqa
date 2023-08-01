<script>
import { mapState, mapActions, mapMutations } from 'vuex';
import djangoRest from '@/django';
import JsonDataTable from '../components/JsonDataTable';
import { AIDA_SERVER } from '../constants';

export default {
  name: 'ImageView',
  components: {
    JsonDataTable,
  },
  inject: ['user'],
  data: () => ({
    segmentImageUrl: '',
    headers: [
      { text: 'ARMS', value: 'ARMS', align: 'right', color: 'rgb(0,0,255)' },
      { text: 'ERMS', value: 'ERMS', align: 'right', color: 'rgb(255,0,0)' },
      { text: 'nacorsis', value: 'nacorsis', align: 'right', color: 'rgb(255,255,0)' },
      { text: 'stroma', value: 'stroma', align: 'right', color: 'rgb(0,255,0)' }
    ]
  }),
  computed: {
    ...mapState(['currentProject', 'allUsers', 'scans', 'selectedScan', 'scanFrames', 'frames', 'hasSegAnalysis']),
    permissions() {
      return this.currentProject.settings.permissions;
    },
    scanName () {
      return this.scans[this.selectedScan].name;
    },
    segTable () {
      let segAnalysis = this.scans[this.selectedScan].analysis;
      if (segAnalysis.length !== 0 && segAnalysis.filter(a => a.analysis_type=='SEGMENT')[0].status == 3) {
        let data = [JSON.parse(this.scans[this.selectedScan].analysis.filter(a => a.analysis_type=='SEGMENT')[0].analysis_result)];
        data.columns = ['ARMS','ERMS','necrosis','stroma'];
        // render by updating the this.table model
        let table = data;
        console.log(table)
        return table;
      }
      return [];
    },
    // inputImageUrl() {
    //   console.log(this.selectedScan)
    //   return 'blob:http://localhost:8000/test' + this.selectedScan;
    // }
  },
  asyncComputed: {
    inputImageUrl: {
      // get Seg if exist
      // 
      // 
      //
      // inputimage url not update if it is running??
      // 
      // 
      get () {

        // update scan frames after seg finish




        if (this.scanFrames[this.selectedScan][1]) {
          djangoRest.downloadThumbnail(this.scanFrames[this.selectedScan][1]).then((response) => {
            this.segmentImageUrl = window.URL.createObjectURL(response);
          }).catch((err) => {
            console.error('Segmentation result is not ready yet.');
          });
        }
        return djangoRest.downloadThumbnail(this.scanFrames[this.selectedScan][0]).then(response =>  window.URL.createObjectURL(response));
      }
      // default () {
      //   return 'http://localhost:8000/test'
      // }
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
    AIDAviewer () {
      window.open(AIDA_SERVER + '?imageId=' + this.scans[this.selectedScan].name);
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
    }
  },
};
</script>

<template>
  <v-card class="flex-card"
          min-width=820>
    <v-subheader><b>{{scanName}}</b>: Image and Segmentation</v-subheader>
    <v-container class="pl-2 pr-2">
      <div>
        <img :src="inputImageUrl" width="400" height="300" style="margin: auto;cursor: zoom-in;" @click="AIDAviewer()"> 
        <img v-if="hasSegAnalysis" :src="segmentImageUrl" width="400" height="300" style="margin: auto"> 
      </div>
      <div v-if="segTable.length > 0" class="mt-8 mb-4 ml-4 mr-4">
        <v-card-text>Image Statistics</v-card-text>
        <template>
          <v-data-table
            :items="segTable"
          >
            <template v-slot:header="{ props, on }">
              <th style="text-align: left;" v-for="head in headers">
                <span class="box" :style="{'background-color':head.color}"></span>
                {{ head.text }}
              </th>
            </template>
            <template v-slot:item="{ item }">
              <tr>
                <td class="text-start" v-for="column in segTable.columns" v-bind:key="column">
                  {{ item[column].toFixed(2) }} %
                </td>
              </tr>
            </template>
          </v-data-table>
        </template>
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
.box {
  float: left;
  height: 20px;
  width: 20px;
  clear: both;
}
</style>
