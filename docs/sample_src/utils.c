#include <stdlib.h>

int *get_value(int flag) {
    int *p = malloc(sizeof(int));
    if (flag) {
        *p = 42;
        return p;
    }
    free(p);
    return p; // USE_AFTER_FREE if flag false
}
