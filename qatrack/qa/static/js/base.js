/**************************************************************************/
//Initialize sortable/filterable test list table data types
function init_test_collection_tables(){
	var selector;
	if (arguments.length === 0){
		selector = ".test-collection-table";
	}else{
		selector = arguments[0];
	}
	$(selector).each(function(idx,table){
		var cols ;

		if ($(table).hasClass("review-table")){
			cols = [
				null, //Unit
				null, //Freq
				null,  // Test list name
				{"sType":"day-month-year-sort"}, //date completed
				{"sType":"span-day-month-year-sort"}, //due date
				null, //status of test list tests
				null,  //review status of list
				null  //history
			];
			filter_cols =  [
				{type: "select"}, //Unit
				{type: "select"}, //Freq
				{type: "text" }, // Test list name
				{type: "text" }, //date completed
				{type: "text" }, //due date
				{ type: "text" }, //status of test list tests
				null, //review status of list
				null  //history
			];
		}else{
			cols = [
				null, //Unit
				null, //Freq
				null,  // Test list name
				{"sType":"day-month-year-sort"}, //date completed
				{"sType":"span-day-month-year-sort"}, //due date
				null, //qa status
				null,//assigned to
				null //perform link
			];
			filter_cols = [
				{type: "select"}, //Unit
				{type: "select"}, //Freq
				{type: "text" }, // Test list name
				{type: "text" }, //date completed
				{type: "text" }, //due date
				null, //qa status
				{type: "select"},//assigned to
				null //perform link
			];
		}

		$(table).dataTable( {
			"sDom": "t<'row-fluid'<'span3'><'span3' l><'span6'p>>",

			"bStateSave":false, //save filter/sort state between page loads
			"bFilter":true,
			"bPaginate": false,

			aoColumns: cols

		}).columnFilter({
			sPlaceHolder: "head:after",
			aoColumns: filter_cols
		});

		$(table).find("select, input").addClass("input-small");

	});

}

/**************************************************************************/
$(document).ready(function(){

	$.when(QAUtils.init()).done(function(){
		init_test_collection_tables();

		$(".test-collection-table tbody tr.has-due-date").each(function(idx,row){
			var date_string = $(this).data("last_done");
			var last_done = null;
			if (date_string){
				last_done = QAUtils.parse_iso8601_date(date_string);
			}
			var freq = $(this).data("frequency");
			QAUtils.set_due_status_color($(this).find(".due-status"),last_done,freq);
		});
	});
});