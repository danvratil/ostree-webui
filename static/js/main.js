 $(document).ready(function(){
    $('.gallery-thumbnail').on('click',function(){
        var src = $(this).attr('src');
        var img = '<img src="' + src + '" class="img-responsive center-block"/>';
        $('#gallery-modal').modal();
        $('#gallery-modal').on('shown.bs.modal', function(){
            $('#gallery-modal .modal-body').html(img);
        });
        $('#gallery-modal').on('hidden.bs.modal', function(){
            $('#gallery-modal .modal-body').html('');
        });
    })

    $('[data-toggle="tooltip"]').tooltip()
})