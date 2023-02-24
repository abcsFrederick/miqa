<template>
<v-data-table
  :headers="data.columns.map(d => ({text: d, value: d}))"
  :items="data"
>
  <template v-slot:item="props">
  	<tr>
	    <td class="text-start" v-for="column in data.columns" v-bind:key="column">
	      {{ props.item[column].toFixed(3) }}
	    </td>
	</tr>
  </template>
</v-data-table>
</template>
<script>
export default {
  name: 'json-data-table',
  props: ['data'],
};
</script>
