<?php

$config = new PhpCsFixer\Config();

return $config
    ->setRiskyAllowed(true)
    ->setRules([
        '@PSR12' => true,
        '@PHP80Migration' => true,

        // WordPress-specific preferences
        'binary_operator_spaces' => ['default' => 'align_single_space'], // Align assignments/operators
        'single_quote' => false, // WP prefers double quotes
        'concat_space' => ['spacing' => 'one'], // Spaces around concat operator
        'array_syntax' => ['syntax' => 'long'], // WP avoids short array []
        'blank_line_before_statement' => [
            'statements' => ['return', 'throw', 'try'],
        ],

        // DocBlock tweaks (closer to WP coding standards)
        'phpdoc_align' => false,
        'phpdoc_annotation_without_dot' => false,
        'phpdoc_no_package' => true,
        'phpdoc_scalar' => true,
        'phpdoc_trim' => true,
        'phpdoc_types' => true,

        // Extra polish
        'cast_spaces' => ['space' => 'single'],
        'no_trailing_comma_in_singleline_array' => true,
        'no_empty_phpdoc' => true,
        'no_extra_blank_lines' => ['tokens' => ['extra']],
    ])
    ->setFinder(
        PhpCsFixer\Finder::create()
            ->in(__DIR__)
            ->exclude('vendor')
    );

