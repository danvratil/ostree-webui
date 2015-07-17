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
    });

    $('[data-toggle="tooltip"]').tooltip();

    $('.browser-icon').hover(
        function () {
            $(this).removeClass('glyphicon-folder-close')
            $(this).addClass('glyphicon-folder-open');
        },
        function () {
            $(this).removeClass('glyphicon-folder-open')
            $(this).addClass('glyphicon-folder-close');
        }
    );

    $('pre.with-line-numbers').each(function() {
        $(this).html('<span class="line-number"></span>' + $(this).html() + '<span class="cl"></span>');
        var code = $(this).find('code')[0]
        var codehtml = $(code).html().split('\n')
        newcodehtml = ''
        for (var i = 0; i < codehtml.length; i++) {
            newcodehtml += '<span class="code-line">&zwnj;' + codehtml[i] + '</span>\n';
        }
        $(code).html(newcodehtml)
        for (var j = 0; j < codehtml.length; j++) {
            var line_num = $(this).find('span')[0];
            $(line_num).html($(line_num).html() + '<span>' + (j + 1) + '</span>');
        }
    });

    $('pre.with-line-numbers span.line-number span:odd, \
       pre.with-line-numbers span.code-line:odd').css('background-color', '#E1E1E1');
})