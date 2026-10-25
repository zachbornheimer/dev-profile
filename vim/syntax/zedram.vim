" Vim syntax file
" Language: ZEDRAM
" Maintainer: Z. Bornheimer (ZYSYS)
" Latest Revision: October 1, 2020

if exists("b:current_syntax")
  finish
endif

set iskeyword+=-
syntax match zedramOperator "\v END"
syntax match zedramOperator "\v/"
syntax match zedramOperator "\v,"
syntax keyword zedramFunction open define\-each exec close set set-attr
syntax match zedramComment "\v\(comment.*\)$"


highlight link zedramKeyword Keyword
highlight link zedramSlashDefineEach Constant
highlight link zedramFunction Function
highlight link zedramOperator Operator
highlight link zedramComment Comment



let b:current_syntax = 'zedram'
