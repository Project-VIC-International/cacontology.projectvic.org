<script>
$("#menu-toggle").click(function(e) {
    e.preventDefault();
    $("#wrapper").toggleClass("toggled");
});
</script>

<script type="text/javascript">

$('#search-input-sidebar').keyup(function() {

  var val = $.trim($(this).val()).replace(/ +/g, ' ').toLowerCase();
  // var $rows = $(this).next(".entities-list").find("div");
  var $rows = $(this).parent().parent().find("li.second-level");

  $rows.show().filter(function() {
      var text = $(this).text().replace(/\s+/g, ' ').toLowerCase();
      return !~text.indexOf(val);
  }).hide();
});

</script>