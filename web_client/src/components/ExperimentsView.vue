<script>
import _ from 'lodash';
import {
  mapState, mapGetters, mapMutations, mapActions,
} from 'vuex';
import UserAvatar from '@/components/UserAvatar.vue';
import djangoRest from '@/django';
import { includeScan } from '@/store';
import { API_URL, decisionOptions } from '../constants';

export default {
  name: 'ExperimentsView',
  components: { UserAvatar },
  inject: ['user', 'MIQAConfig'],
  props: {
    minimal: {
      type: Boolean,
      default: false,
    },
  },
  data: () => ({
    API_URL,
    showUploadModal: false,
    showDeleteModal: false,
    uploadToExisting: false,
    uploadError: '',
    experimentNameForUpload: '',
    fileSetForUpload: [],
    uploading: false,
    decisionOptions,
    runableScan: 1,
    selectAnalysis: 'myod1',
    headers: [
      { text: 'Experiment', value: 'experimentName', align: 'left' },
      { text: 'Scan', value: 'name', align: 'left' },
      { text: 'Segmentation', value: 'seg_highest', align: 'left' },
      { text: 'MyoD1', value: 'myod1_score', align: 'left' },
      { text: 'Survivability', value: 'surv_score', align: 'left' },
      { text: 'Subtype', value: 'subtype_score', align: 'left' },
      { text: 'Tp53', value: 'tp53_score', align: 'left' }
    ]
  }),
  computed: {
    ...mapState([
      'reviewMode',
      'experiments',
      'experimentIds',
      'experimentScans',
      'loadingExperiment',
      'scans',
      'scanFrames',
      'frames',
      'currentTaskOverview',
      'currentProject',
      'allExperiments',
      'me',
      'currentProjectPermissions',
      'selectedExperiments'
    ]),
    ...mapGetters(['currentScan', 'currentExperiment']),
    orderedExperiments() {
      return this.experimentIds.map((expId) => this.experiments[expId]);
    },
    loadingIcon() {
      return this.loadingExperiment
        ? 'mdi-progress-clock'
        : 'mdi-check-circle-outline';
    },
    loadingIconColor() {
      return this.loadingExperiment ? 'red' : 'green';
    },
    scansForExperiments() {
      this.allScans = [];
      for (let a = 0; a < this.experimentIds.length; a++) {
        let expId = this.experimentIds[a];
        let expScanIds = this.experimentScans[expId];
        let experimentName = this.experiments[expId]['name'];
        let experiment_lockOwner = this.experiments[expId]['lockOwner'];
        expScanIds.filter(
          (scanId) => Object.keys(this.scans).includes(scanId),
        ).map((scanId) => {
          const scan = this.scans[scanId];
          let seg_highest = '';
          let myod1_score = '';
          let surv_score = '';
          let subtype_score = '';
          let tp53_score = '';
          let status = ''
          let result_obj;
          scan.analysis.forEach(an => {
            // console.log(an)
            switch (an.analysis_type) {
              case 'SEGMENT':
                if (an.status === 3) {
                  result_obj = JSON.parse(an.analysis_result);
                  let score_max = Math.max(...Object.values(result_obj));
                  seg_highest = Object.keys(result_obj).find(key => result_obj[key] === score_max)
                } else if (an.status === 2) {
                  seg_highest = 'Running';
                } else if (an.status === 4) {
                  seg_highest = 'Fail';
                }
                break;
              case 'MYOD1':
                if (an.status === 3) {
                  result_obj = JSON.parse(an.analysis_result)
                  myod1_score = result_obj['Positive Score'].toFixed(3);
                } else if (an.status === 2) {
                  myod1_score = 'Running';
                } else if (an.status === 4) {
                  myod1_score = 'Fail';
                }
                break;
              case 'SURVIVABILITY':
                if (an.status === 3) {
                  result_obj = JSON.parse(an.analysis_result);
                  surv_score = result_obj['secondBest'].toFixed(3);
                } else if (an.status === 2) {
                  surv_score = 'Running';
                } else if (an.status === 4) {
                  surv_score = 'Fail';
                }
                break;
              case 'SUBTYPE':
                if (an.status === 3) {
                  result_obj = JSON.parse(an.analysis_result);
                  subtype_score = result_obj['Subtype'];
                } else if (an.status === 2) {
                  subtype_score = 'Running';
                } else if (an.status === 4) {
                  subtype_score = 'Fail';
                }
                break;
              case 'TP53':
                if (an.status === 3) {
                  result_obj = JSON.parse(an.analysis_result);
                  tp53_score = result_obj['tp53 score'].toFixed(3);
                } else if (an.status === 2) {
                  tp53_score = 'Running';
                } else if (an.status === 4) {
                  tp53_score = 'Fail';
                }
                break;
            }
            // if (an.status === 3 && an.analysis_type === 'SEGMENT') {
            //   let result_obj = JSON.parse(an.analysis_result);
            //   let score_max = Math.max(...Object.values(result_obj));
            //   seg_highest = Object.keys(result_obj).find(key => result_obj[key] === score_max)
            // }
            // if (an.status === 3 && an.analysis_type === 'MYOD1') {
            //   let result_obj = JSON.parse(an.analysis_result)
            //   myod1_score = result_obj['Positive Score'];
            // }
          })
          this.allScans.push({
            experimentName,
            experiment_lockOwner,
            seg_highest,
            myod1_score,
            surv_score,
            subtype_score,
            tp53_score,
            ...scan,
            ...this.decisionToRating(scan.decisions),
          });
        });
      }
      return this.allScans;
    },
  },
  watch: {
    showUploadModal() {
      this.delayPrepareDropZone();
    },
    currentProject() {
      this.showUploadModal = false;
      this.uploadToExisting = false;
      this.uploadError = '';
      this.fileSetForUpload = [];
      this.uploading = false;
    },
    allExperiments(e) {
      if (e) {
        // this.selectedExperiments = this.experimentIds;
      } else {
        this.selectedExperiments = {};
      }
    }
  },
  methods: {
    ...mapMutations([
      'switchReviewMode',
      'switchAllExperiments'
    ]),
    ...mapActions([
      'loadProject',
    ]),
    includeScan,
    scansForExperiment(expId) {
      const expScanIds = this.experimentScans[expId];
      return expScanIds.filter(
        (scanId) => Object.keys(this.scans).includes(scanId),
      ).map((scanId) => {
        const scan = this.scans[scanId];
        return {
          ...scan,
          ...this.decisionToRating(scan.decisions),
        };
      });
    },
    ellipsisText(str) {
      if (!this.minimal) return str;
      if (str.length > 25) {
        return `${str.substr(0, 10)}...${str.substr(
          str.length - 10, str.length,
        )}`;
      }
      return str;
    },
    getURLForScan(scanId) {
      return `/${this.currentProject.id}/${scanId}`;
    },
    decisionToRating(decisions) {
      if (decisions.length === 0) return {};
      const rating = _.first(_.sortBy(decisions, (dec) => dec.created)).decision;
      let color = 'grey--text';
      if (rating === 'U') {
        color = 'green--text';
      }
      if (rating === 'UN') {
        color = 'red--text';
      }
      return {
        decision: rating,
        color,
      };
    },
    scanIsCurrent(scan) {
      if (scan === this.currentScan) {
        return ' current';
      }
      return '';
    },
    scanState(scan) {
      let state;
      if (this.currentTaskOverview) {
        state = this.currentTaskOverview.scan_states[scan.id];
      }
      return state || 'unreviewed';
    },
    scanStateClass(scan) {
      let classes = `body-1 state-${this.scanState(scan).replace(/ /g, '-')}`;
      if (scan === this.currentScan) {
        classes = `${classes} current`;
      }
      return classes;
    },
    delayPrepareDropZone() {
      setTimeout(this.prepareDropZone, 500);
    },
    prepareDropZone() {
      const dropZone = document.getElementById('dropZone');
      if (dropZone) {
        dropZone.addEventListener('dragenter', (e) => {
          e.preventDefault();
          dropZone.classList.add('hover');
        });
        dropZone.addEventListener('dragleave', (e) => {
          e.preventDefault();
          dropZone.classList.remove('hover');
        });
      }
    },
    addDropFiles(e) {
      this.fileSetForUpload = [...e.dataTransfer.files];
    },
    async uploadToExperiment() {
      let experimentId;
      this.uploading = true;
      try {
        if (!this.uploadToExisting) {
          const newExperiment = await djangoRest.createExperiment(
            this.currentProject.id, this.experimentNameForUpload,
          );
          experimentId = newExperiment.id;
        } else {
          experimentId = Object.values(this.experiments).find(
            (experiment) => experiment.name === this.experimentNameForUpload,
          ).id;
        }
        await djangoRest.uploadToExperiment(experimentId, this.fileSetForUpload);
        this.loadProject(this.currentProject);
        this.showUploadModal = false;
      } catch (ex) {
        const text = ex || 'Upload failed due to server error.';
        this.uploadError = text;
      }
      this.uploading = false;
    },
    deleteExperiment(experimentId) {
      djangoRest.deleteExperiment(experimentId).then(
        () => {
          this.loadProject(this.currentProject);
          this.showDeleteModal = false;
        },
      );
    },
    seg_analysis() {
      let experiments = this.experimentsForAnalysis();
      djangoRest.runSegment(experiments).then(res => {
        this.$store.commit('updateAlert', {type: 'info', message: res});
      });
    },
    myod1_analysis() {
      let experiments = this.experimentsForAnalysis();
      djangoRest.runMyoD1(experiments);
    },
    survivability_analysis() {
      let experiments = this.experimentsForAnalysis();
      djangoRest.runSurvivability(experiments);
    },
    subtype_analysis() {
      let experiments = this.experimentsForAnalysis();
      djangoRest.runSubtype(experiments);
    },
    tp53_analysis() {
      let experiments = this.experimentsForAnalysis();
      djangoRest.runTP53(experiments);
    },
    experimentsForAnalysis() {
      var filtered = Object.keys(this.selectedExperiments).filter(function(key) {
        return this.selectedExperiments[key]
      }.bind(this));
      return this.allExperiments ? this.experimentIds : filtered;
    },
    selectScan(e) {
      this.$store.commit('updateSelectScan', e.currentTarget.getAttribute('data-id'))
    },
    // Current displayed scans
    currentItems(scans) {
      this.$store.commit('setScans', scans)
    }
  },
};
</script>

<template>
  <v-card
    v-if="currentProject"
    class="flex-card"
  >
    <div
      v-if="currentProject"
      class="d-flex"
      style="justify-content: space-between; align-items: baseline"
    >
      <v-subheader
        v-if="!minimal"
        style="display: inline"
      >
        Experiments
      </v-subheader>
      <v-subheader
        class="mode-toggle"
      >
        <span>Run analysis for selected experiments</span>
        <v-switch
          :input-value="allExperiments"
          dense
          style="display: inline-block; max-height: 40px; max-width: 60px;"
          class="px-3 ma-0"
          @change="switchAllExperiments"
        />
        <span>All experiments</span>
      </v-subheader>
    </div>
    <div class="scans-view">
      <div style="width: 80%" v-if="orderedExperiments && orderedExperiments.length">
        <ul class="experiment">
          <v-data-table
            :headers="headers"
            :items="scansForExperiments"
            group-by="experimentName"
            class="elevation-1"
            :items-per-page=5
            @current-items="currentItems"
          >
            <template v-slot:top>
              <v-dialog
                v-if="!minimal && MIQAConfig.S3_SUPPORT"
                v-model="showUploadModal"
                width="600px"
              >
                <template v-slot:activator="{ on, attrs }">
                  <div
                    v-bind="attrs"
                    class="add-scans"
                    v-on="on"
                  >
                    <v-btn
                      class="green white--text"
                      @click="() => {experimentNameForUpload = ''}"
                    >
                      + Add Scans...
                    </v-btn>
                  </div>
                </template>
                <v-card>
                  <v-btn
                    icon
                    style="float:right"
                    @click="showUploadModal=false"
                  >
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
                  <v-card-title class="text-h6">
                    Upload Image Files to Experiment
                  </v-card-title>
                  <div
                    class="d-flex px-6"
                    style="align-items: baseline; justify-content: space-between;"
                  >
                    <div
                      class="d-flex mode-toggle"
                    >
                      <span>Upload to New</span>
                      <v-switch
                        :value="uploadToExisting"
                        :disabled="!(orderedExperiments && orderedExperiments.length)"
                        inset
                        dense
                        style="display: inline-block; max-height: 40px; max-width: 60px;"
                        class="px-3 ma-0"
                        @change="(value) => {uploadToExisting = value; experimentNameForUpload = ''}"
                      />
                      <span
                        :class="!(orderedExperiments && orderedExperiments.length) ? 'grey--text' : ''"
                      >
                        Upload to Existing
                      </span>
                    </div>
                    <div style="max-width:200px">
                      <v-select
                        v-if="orderedExperiments && orderedExperiments.length && uploadToExisting"
                        v-model="experimentNameForUpload"
                        :items="orderedExperiments"
                        item-text="name"
                        label="Select Experiment"
                        dense
                      />
                      <v-text-field
                        v-else
                        v-model="experimentNameForUpload"
                        label="Name new Experiment"
                      />
                    </div>
                  </div>
                  <div class="ma-5">
                    <v-file-input
                      v-model="fileSetForUpload"
                      label="Image files (.nii.gz, .nii, .mgz, .nrrd, .svs, .tif, .png)"
                      prepend-icon="mdi-paperclip"
                      multiple
                      chips
                      @click:clear="delayPrepareDropZone"
                    >
                      <template #selection="{ index, text }">
                        <v-chip
                          v-if="index < 2"
                          small
                        >
                          {{ text }}
                        </v-chip>

                        <span
                          v-else-if="index === 2"
                          class="text-overline grey--text text--darken-3 mx-2"
                        >
                          +{{ fileSetForUpload.length - 2 }}
                          file{{ fileSetForUpload.length - 2 > 1 ? 's' :'' }}
                        </span>
                      </template>
                    </v-file-input>
                    <div
                      v-if="fileSetForUpload.length == 0"
                      id="dropZone"
                      style="text-align: center"
                      class="pa-3 drop-zone"
                      @drop.prevent="addDropFiles"
                      @dragover.prevent
                    >
                      or drag and drop here
                    </div>
                  </div>
                  <v-divider />
                  <v-card-actions>
                    <div
                      v-if="uploadError"
                      style="color: red;"
                    >
                      {{ uploadError }}
                    </div>
                    <v-spacer />
                    <v-btn
                      :loading="uploading"
                      :disabled="fileSetForUpload.length < 1 || !experimentNameForUpload"
                      color="primary"
                      text
                      @click="uploadToExperiment()"
                    >
                      Upload
                    </v-btn>
                  </v-card-actions>
                </v-card>
              </v-dialog>
            </template>
            <template v-slot:group.header="{items, isOpen, toggle}">
              <th colspan="7">
                <v-checkbox
                  :model-value=items[0].experiment
                  v-model=selectedExperiments[items[0].experiment]
                  :disabled="allExperiments == true">
                    <template v-slot:label>
                      {{ items[0].experimentName }}
                      <!--<v-icon @click="toggle"
                        >{{ isOpen ? 'mdi-minus-circle-outline' : 'mdi-plus-circle-outline' }}
                      </v-icon>-->
                      <UserAvatar
                        v-if="items[0].experiment_lockOwner"
                        :target-user="items[0].experiment_lockOwner"
                        as-editor
                      />
                      <v-dialog
                        v-else-if="!minimal"
                        :value="showDeleteModal === items[0].experiment"
                        width="600px"
                      >
                        <template #activator="{ attrs }">
                          <div
                            v-bind="attrs"
                            style="display: inline"
                            @click="showDeleteModal = items[0].experiment"
                          >
                            <v-icon>mdi-delete</v-icon>
                          </div>
                        </template>

                        <v-card>
                          <v-btn
                            icon
                            style="float:right"
                            @click="showDeleteModal=false"
                          >
                            <v-icon>mdi-close</v-icon>
                          </v-btn>
                          <v-card-title class="text-h6">
                            Confirmation
                          </v-card-title>
                          <v-card-text>
                            Are you sure you want to delete experiment {{ items[0].experimentName }}?
                          </v-card-text>
                          <v-divider />
                          <v-card-actions>
                            <v-btn
                              :loading="uploading"
                              color="gray"
                              text
                              @click="() => showDeleteModal = false"
                            >
                              Cancel
                            </v-btn>
                            <v-btn
                              :loading="uploading"
                              color="red"
                              text
                              @click="() => deleteExperiment(items[0].experiment)"
                            >
                              Delete
                            </v-btn>
                          </v-card-actions>
                        </v-card>
                      </v-dialog>

                    </template>
                  </v-checkbox>
              </th>
            </template>
            <template v-slot:item="{ item }">
              <tr :data-id="item.id" @click="selectScan">
                <td>
                  {{item.name}}
                </td>
                <td v-if="item.seg_highest === 'Running' ">
                  <v-icon color="orange">mdi-loading mdi-spin</v-icon>
                </td>
                <td v-else-if="item.seg_highest === 'Fail' ">
                  <v-icon color="red">mdi-close-thick</v-icon>
                </td>
                <td v-else>
                  {{item.seg_highest}}
                </td>
                <td v-if="item.myod1_score === 'Running' ">
                  <v-icon color="orange">mdi-loading mdi-spin</v-icon>
                </td>
                <td v-else-if="item.myod1_score === 'Fail' ">
                  <v-icon color="red">mdi-close-thick</v-icon>
                </td>
                <td v-else>
                  {{item.myod1_score}}
                </td>
                <td v-if="item.surv_score === 'Running' ">
                  <v-icon color="orange">mdi-loading mdi-spin</v-icon>
                </td>
                <td v-else-if="item.surv_score === 'Fail' ">
                  <v-icon color="red">mdi-close-thick</v-icon>
                </td>
                <td v-else>
                  {{item.surv_score}}
                </td>

                <td v-if="item.subtype_score === 'Running' ">
                  <v-icon color="orange">mdi-loading mdi-spin</v-icon>
                </td>
                <td v-else-if="item.subtype_score === 'Fail' ">
                  <v-icon color="red">mdi-close-thick</v-icon>
                </td>
                <td v-else>
                  {{item.subtype_score}}
                </td>

                <td v-if="item.tp53_score === 'Running' ">
                  <v-icon color="orange">mdi-loading mdi-spin</v-icon>
                </td>
                <td v-else-if="item.tp53_score === 'Fail' ">
                  <v-icon color="red">mdi-close-thick</v-icon>
                </td>
                <td v-else>
                  {{item.tp53_score}}
                </td>
              </tr>
            </template>
          </v-data-table>
          <!--<li
            v-for="experiment of orderedExperiments"
            :key="`e.${experiment.id}`"
            class="body-2 pb-5"
          >
            <v-card
              flat
              class="d-flex pr-2"
            >
              <v-row align="center" m=0>
                <v-checkbox
                v-model='selectedExperiments'
                :value="experiment.id"
                :style="{visibility: allExperiments ? 'hidden' : 'visible'}"></v-checkbox>
                <v-card flat>
                  {{ ellipsisText(experiment.name) }}
                  <UserAvatar
                    v-if="experiment.lock_owner"
                    :target-user="experiment.lock_owner"
                    as-editor
                  />
                  <v-dialog
                    v-else-if="!minimal"
                    :value="showDeleteModal === experiment.id"
                    width="600px"
                  >
                    <template #activator="{ attrs }">
                      <div
                        v-bind="attrs"
                        style="display: inline"
                        @click="showDeleteModal = experiment.id"
                      >
                        <v-icon>mdi-delete</v-icon>
                      </div>
                    </template>

                    <v-card>
                      <v-btn
                        icon
                        style="float:right"
                        @click="showDeleteModal=false"
                      >
                        <v-icon>mdi-close</v-icon>
                      </v-btn>
                      <v-card-title class="text-h6">
                        Confirmation
                      </v-card-title>
                      <v-card-text>
                        Are you sure you want to delete experiment {{ experiment.name }}?
                      </v-card-text>
                      <v-divider />
                      <v-card-actions>
                        <v-btn
                          :loading="uploading"
                          color="gray"
                          text
                          @click="() => showDeleteModal = false"
                        >
                          Cancel
                        </v-btn>
                        <v-btn
                          :loading="uploading"
                          color="red"
                          text
                          @click="() => deleteExperiment(experiment.id)"
                        >
                          Delete
                        </v-btn>
                      </v-card-actions>
                    </v-card>
                  </v-dialog>
                </v-card>
              </v-row>
              <v-card flat>
                <v-icon
                  v-show="experiment === currentExperiment"
                  :color="loadingIconColor"
                  class="pl-5"
                >
                  {{ loadingIcon }}
                </v-icon>
              </v-card>
            </v-card>
            <ul class="scans">
              <li
                v-for="scan of scansForExperiment(experiment.id)"
                :key="`s.${scan.id}`"
                :class="scanStateClass(scan)"
              >
                <v-tooltip right>
                  <template #activator="{ on, attrs }">
                    <v-btn
                      v-bind="attrs"
                      :disabled="!includeScan(scan.id)"
                      class="ml-0 px-1 scan-name"
                      href
                      text
                      small
                      active-class=""
                      v-on="on"
                      :scan-id="scan.id"
                      @click="selectScan"
                    >
                      <span v-for="an of scan.analysis">
                        <v-icon v-if="an.status === 3 && an.analysis_type === 'SEGMENT'" 
                        color="blue">mdi-image</v-icon>
                        <v-icon v-if="an.status === 3 && an.analysis_type === 'MYOD1'" 
                        color="red">mdi-alpha-m-circle-outline</v-icon>
                        <v-icon v-if="an.status === 3 && an.analysis_type === 'SURVIVABILITY'" 
                        color="green">mdi-alpha-s-circle-outline</v-icon>
                        <v-icon v-if="an.status === 4" 
                        color="red">mdi-close-thick</v-icon>
                        <v-icon v-if="an.status === 2" 
                        color="orange">mdi-loading mdi-spin</v-icon>
                      </span>
                      {{ ellipsisText(scan.name) }}
                      <span
                        v-if="scan.decisions.length !== 0"
                        :class="scan.color + ' pl-3'"
                        small
                      >({{ scan.decision }})</span>
                    </v-btn>
                  </template>
                  <span>
                    {{ scan.decision ? decisionOptions[scan.decision] +', ' : '' }}
                    {{ scanState(scan) }}
                  </span>
                </v-tooltip>
              </li>
            </ul>
          </li>
        -->
        </ul>
      </div>
      <div
        v-else-if="currentProject.experiments.length"
        class="pa-5"
        style="width: 60%; text-align: center"
      >
        <v-progress-circular indeterminate />
      </div>
      <div
        v-else
        class="pa-5"
        style="width: max-content"
      >
        <span class="px-5">No imported data.</span>
      </div>
      <!--<v-dialog
        v-if="!minimal && MIQAConfig.S3_SUPPORT"
        v-model="showUploadModal"
        width="600px"
      >
        <template #activator="{ on, attrs }">
          <div
            v-bind="attrs"
            class="add-scans"
            v-on="on"
          >
            <v-btn
              class="green white--text"
              @click="() => {experimentNameForUpload = ''}"
            >
              + Add Scans...
            </v-btn>
          </div>
        </template>
        <v-card>
          <v-btn
            icon
            style="float:right"
            @click="showUploadModal=false"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
          <v-card-title class="text-h6">
            Upload Image Files to Experiment
          </v-card-title>
          <div
            class="d-flex px-6"
            style="align-items: baseline; justify-content: space-between;"
          >
            <div
              class="d-flex mode-toggle"
            >
              <span>Upload to New</span>
              <v-switch
                :value="uploadToExisting"
                :disabled="!(orderedExperiments && orderedExperiments.length)"
                inset
                dense
                style="display: inline-block; max-height: 40px; max-width: 60px;"
                class="px-3 ma-0"
                @change="(value) => {uploadToExisting = value; experimentNameForUpload = ''}"
              />
              <span
                :class="!(orderedExperiments && orderedExperiments.length) ? 'grey--text' : ''"
              >
                Upload to Existing
              </span>
            </div>
            <div style="max-width:200px">
              <v-select
                v-if="orderedExperiments && orderedExperiments.length && uploadToExisting"
                v-model="experimentNameForUpload"
                :items="orderedExperiments"
                item-text="name"
                label="Select Experiment"
                dense
              />
              <v-text-field
                v-else
                v-model="experimentNameForUpload"
                label="Name new Experiment"
              />
            </div>
          </div>
          <div class="ma-5">
            <v-file-input
              v-model="fileSetForUpload"
              label="Image files (.nii.gz, .nii, .mgz, .nrrd, .svs, .tif, .png)"
              prepend-icon="mdi-paperclip"
              multiple
              chips
              @click:clear="delayPrepareDropZone"
            >
              <template #selection="{ index, text }">
                <v-chip
                  v-if="index < 2"
                  small
                >
                  {{ text }}
                </v-chip>

                <span
                  v-else-if="index === 2"
                  class="text-overline grey--text text--darken-3 mx-2"
                >
                  +{{ fileSetForUpload.length - 2 }}
                  file{{ fileSetForUpload.length - 2 > 1 ? 's' :'' }}
                </span>
              </template>
            </v-file-input>
            <div
              v-if="fileSetForUpload.length == 0"
              id="dropZone"
              style="text-align: center"
              class="pa-3 drop-zone"
              @drop.prevent="addDropFiles"
              @dragover.prevent
            >
              or drag and drop here
            </div>
          </div>
          <v-divider />
          <v-card-actions>
            <div
              v-if="uploadError"
              style="color: red;"
            >
              {{ uploadError }}
            </div>
            <v-spacer />
            <v-btn
              :loading="uploading"
              :disabled="fileSetForUpload.length < 1 || !experimentNameForUpload"
              color="primary"
              text
              @click="uploadToExperiment()"
            >
              Upload
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>-->
      <v-card style="box-shadow:none; width: 20%" class="pl-2 pr-3">
        <v-row class="analysis">
          <v-btn
            class="blue white--text"
            style="margin-bottom: 4px"
            @click="seg_analysis"
          >
              <v-icon>mdi-numeric-1-box</v-icon>
              Segmentation
          </v-btn>
        </v-row>
        <v-row class="analysis">
          <v-btn
            class="blue white--text"
            style="margin-bottom: 4px"
            @click="myod1_analysis"
          >
              <v-icon>mdi-numeric-2-box</v-icon>
              MyoD1
          </v-btn>
        </v-row>
        <v-row class="analysis">
          <v-btn
            class="blue white--text"
            style="margin-bottom: 4px"
            @click="survivability_analysis"
          >
              <v-icon>mdi-numeric-2-box</v-icon>
              Survivability
          </v-btn>
        </v-row>
        <v-row class="analysis">
          <v-btn
            class="blue white--text"
            style="margin-bottom: 4px"
            @click="subtype_analysis"
          >
              <v-icon>mdi-numeric-2-box</v-icon>
              SUBTYPE
          </v-btn>
        </v-row>
        <v-row class="analysis">
          <v-btn
            class="blue white--text"
            style="margin-bottom: 4px"
            @click="tp53_analysis"
          >
              <v-icon>mdi-numeric-2-box</v-icon>
              TP53
          </v-btn>
        </v-row>
      </v-card>
    </div>
  </v-card>
</template>

<style lang="scss" scoped>
.current {
  background: rgb(206, 206, 206);
}
.state-unreviewed::marker {
  color: #1460A3;
  content: '\25C8';
}
.state-needs-tier-2-review::marker {
  color: #6DB1ED;
  content: '\25C8'
}
.state-complete::marker {
  color: #00C853;
  content: '\25C8'
}
li.cached {
  list-style-type: disc;
}
ul.experiment {
  list-style: none;
}
ul.scans {
  padding-left: 15px;
}
.scans-view {
  text-transform: none;
  display: flex;
  flex-flow: row wrap-reverse;
  align-items: baseline;
  justify-content: space-between;
}
.scans-view > div {
  width: min-content;
}
.scan-name .v-btn__content {
  text-transform: none;
}
.mode-toggle {
  align-items: baseline;
  display: inline-block;
}
.add-scans {
  min-width: 150px;
  text-align: right;
  padding-right: 15px;
}
.run-analysis {
  min-width: 150px;
  text-align: right;
  padding-right: 15px;
}
.analysis {
  margin: 0px !important;
}
.drop-zone {
  border: 1px dashed #999999;
}
.drop-zone.hover {
  background-color: rgba(92, 167, 247, 0.5);
}
</style>
