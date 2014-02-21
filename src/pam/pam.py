import bpy
import mathutils.geometry as mug
import mathutils
import math
import numpy as np

# import module for visualization
import pam_vis as pv

# number of samples to compute connection probability
samples = 1000
debug_level = 0


def computeUVScalingFactor(object):
    """computes the scaling factor between uv- and 3d-coordinates for a
    given object
    the return value is the factor that has to be multiplied with the
    uv-coordinates in order to have metrical relation
    """

    result = []

    for i in range(0, len(object.data.polygons)):
        uvs = [object.data.uv_layers.active.data[li] for li in object.data.polygons[i].loop_indices]

        rdist = (object.data.vertices[object.data.polygons[i].vertices[0]].co - object.data.vertices[object.data.polygons[i].vertices[1]].co).length
        mdist = (uvs[0].uv - uvs[1].uv).length
        result.append(rdist/mdist)

    return np.mean(result)
    


# TODO(SK): Quads into triangles (indices)
def map3dPointToUV(object, object_uv, point):
    """Converts a given 3d-point into uv-coordinates,
    object for the 3d point and object_uv must have the same topology
    """

    # get point, normal and face of closest point to particle
    p, n, f = object.closest_point_on_mesh(point)

    # get the uv-coordinate of the first triangle of the polygon
    A = object.data.vertices[object.data.polygons[f].vertices[0]].co
    B = object.data.vertices[object.data.polygons[f].vertices[1]].co
    C = object.data.vertices[object.data.polygons[f].vertices[2]].co

    # and the uv-coordinates of the first triangle
    uvs = [object_uv.data.uv_layers.active.data[li] for li in object_uv.data.polygons[f].loop_indices]
    U = uvs[0].uv.to_3d()
    V = uvs[1].uv.to_3d()
    W = uvs[2].uv.to_3d()

    # convert 3d-coordinates of point p to uv-coordinates
    p_uv = mug.barycentric_transform(p, A, B, C, U, V, W)

    # if the point is not within the first triangle, we have to repeat the calculation
    # for the second triangle
    if mug.intersect_point_tri_2d(p_uv.to_2d(), uvs[0].uv, uvs[1].uv, uvs[2].uv) == 0:
        A = object.data.vertices[object.data.polygons[f].vertices[0]].co
        B = object.data.vertices[object.data.polygons[f].vertices[2]].co
        C = object.data.vertices[object.data.polygons[f].vertices[3]].co

        U = uvs[0].uv.to_3d()
        V = uvs[2].uv.to_3d()
        W = uvs[3].uv.to_3d()

        p_uv = mug.barycentric_transform(p, A, B, C, U, V, W)

    return p_uv.to_2d()


def map3dPointTo3d(o1, o2, point):
    """maps a 3d-point on a given object on another object. Both objects must have the
    same topology
    """

    # get point, normal and face of closest point to particle
    p, n, f = o1.closest_point_on_mesh(point)

    # if o1 and o2 are identical, there is nothing more to do
    if (o1 == o2):
        return p

    # get the vertices of the first triangle of the polygon from both objects
    A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
    B1 = o1.data.vertices[o1.data.polygons[f].vertices[1]].co
    C1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co
    
    # project the point on a 2d-surface and check, whether we are in the right triangle
    t1 = mathutils.Vector()
    t2 = mathutils.Vector((1.0, 0.0, 0.0))
    t3 = mathutils.Vector((0.0, 1.0, 0.0))

    p_test = mug.barycentric_transform(p, A1, B1, C1, t1, t2, t3)

    # if the point is on the 2d-triangle, proceed with the real barycentric_transform
    if mug.intersect_point_tri_2d(p_test.to_2d(), t1.xy, t2.xy, t3.xy) == 1:
        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[1]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co

        # convert 3d-coordinates of the point
        p_new = mug.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    else:

        # use the other triangle
        A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
        B1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co
        C1 = o1.data.vertices[o1.data.polygons[f].vertices[3]].co
        
        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[3]].co

        # convert 3d-coordinates of the point
        p_new = mug.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    # TODO(MP): triangle check could be made more efficient
    # TODO(MP): check the correct triangle order !!!
    return p_new


def connfunc_gauss(u, v, *args):
    """Gauss-function for 2d
    u, v    : coordinates, to determine the function value
    vu, vv  : variance for both dimensions
    su, sv  : shift in u and v direction
    """

    vu = args[0][0]
    vv = args[0][1]
    su = args[0][2]
    sv = args[0][3]

    return math.exp(-((u + su) ** 2 / (2 * vu ** 2) +
                    (v + sv) ** 2 / (2 * vv ** 2)))


def connfunc_unity(u, v, *args):
    return 1

def computeConnectivityProbability(uv1, uv2, func, args):
    return func(uv2[0]-uv1[0], uv2[1]-uv1[1], args)


def computeMapping(layers, connections, distances, point):
    """based on a list of layers, connections-properties and distance-properties,
    this function returns the 3d-point, the 2d-uv-point and the distance from a given
    point on the first layer to the corresponding point on the last layer
    layers              : list of layers connecting the pre-synaptic layer with the synaptic layer
    connections         : list of values determining the type of layer-mapping
    distances           : list of values determining the calculation of the distances between layers
    point               : 3d vector for which the mapping should be calculated
    
    Return values
    -----------------
    p3d                 : list of 3d-vector of the neuron position on all layers
    p2d                 : 2d-vector of the neuron position on the UV map of the last layer
    d                   : distance between neuron position on the first layer and last position before
                          the synapse! This is not the distance to the p3d point! This is either the 
                          distance to the 3d-position of the last but one layer or, in case
                          euclidean-uv-distance was used, the distance to the position of the last
                          layer determind by euclidean-distance. Functions, like computeConnectivity()
                          add the distance to the synapse to value d in order to retrieve
                          the complete distance from the pre- or post-synaptic neuron 
                          to the synapse
    """

    p3d = [point]
    d = 0

    # go through all connection-elements
    for i in range(0, len(connections)):
        # if normal mapping should be computed
        if connections[i] == 0:
            # compute the point on the next intermediate layer
            if (i < (len(connections)-1)):
                p3d_n = map3dPointTo3d(layers[i+1], layers[i+1], p3d[-1])
            # or the last point before the synaptic layer
            else:
                # for euclidean distance
                if distances[i] == 0:
                    p3d_n = p3d[-1]
                # for normal-uv or euclidean-uv mapping
                elif (distances[i] == 1) | (distances[i] == 2):
                    p3d_n = map3dPointTo3d(layers[i+1], layers[i+1], p3d[-1])
        # if both layers are topologically identical
        elif connections[i] == 1:
            # if this is not the last layer, compute the topological mapping
            if (i < (len(connections)-1)):            
                p3d_n = map3dPointTo3d(layers[i], layers[i+1], p3d[-1])
            # if this is the last layer, compute the last p3d-point depending on the 
            # distance value
            else:
                # for euclidean distance
                if distances[i] == 0:
                    # remain at the last position
                    p3d_n = p3d[-1]
                # for normal-uv-distance,     
                elif distances[i] == 1:
                    # get the point on the next layer according to the normal
                    p3d_n = map3dPointTo3d(layers[i+1], layers[i+1], p3d[-1])
                # for euclidean-uv distance
                elif distances[i] == 2:
                    # compute the topologically corresponding point
                    p3d_n = map3dPointTo3d(layers[i], layers[i+1], p3d[-1])


        # compute distance between both points, here according to the euclidean
        if distances[i] == 0:
            if (i < (len(connections)-1)):
                d = d + (p3d[-1] - p3d_n).length            
        
        elif distances[i] == 1:           # compute distance between both points, here according to the euclidean-uv-way
            # if we are not on the last layer
            if (i < (len(connections)-1)):
                # determine closest point on second layer
                p3d_i = layers[i+1].closest_point_on_mesh(p3d[-1])
                p3d_i = p3d_i[0]
                # compute uv-coordintes for euclidean distance and topological mapping
                p2d_i1 = map3dPointToUV(layers[i+1], layers[i+1], p3d[-1])
                p2d_i2 = map3dPointToUV(layers[i+1], layers[i+1], p3d_n)
                # compute distances
                d = d + (p3d[-1] - p3d_i).length  # distance in space between both layers based on euclidean distance
                d = d + (p2d_i1 - p2d_i2).length * layers[i+1]['uv_scaling']  # distance on uv-level (incorporated with scaling parameter)
                p3d.append(p3d_i)
            else:   # if we are in the last layer
                # determine closest point on second layer
                d = d + (p3d[-1] - p3d_n).length  # distance in space between both layers based on euclidean distance
        elif distances[i] == 2:
            # determine closest point on second layer
            d = d + (p3d[-1] - p3d_n).length
            
        # for the synaptic layer, compute the uv-coordinates
        if (i == (len(connections)-1)):
            p2d = map3dPointToUV(layers[i+1], layers[i+1], p3d_n)

        p3d.append(p3d_n)

    return p3d, p2d, d


def computeConnectivity(layers, neuronset1, neuronset2, slayer, connections, distances, func, args):
    """computes the connectivity probability between all neurons of both neuronsets
    on a synaptic layer
    layers              : list of layers connecting a pre- with a post-synaptic layer
    neuronset1,
    neuronset2          : name of the neuronset (particle system) of the pre- and post-synaptic layer
    slayer              : index in layers for the synaptic layer
    connections         : list of values determining the type of layer-mapping
    distances           : list of values determining the calculation of the distances between layers
    func                : function of the connectivity kernel
    args                : argument list for the connectivity kernel
    """

    # connection matrix
    conn = np.zeros((len(layers[0].particle_systems[neuronset1].particles),
                     len(layers[-1].particle_systems[neuronset2].particles)))

    # distance matrix
    dist = np.zeros((len(layers[0].particle_systems[neuronset1].particles),
                     len(layers[-1].particle_systems[neuronset2].particles)))

    for i in range(0, len(layers[0].particle_systems[neuronset1].particles)):
        # compute position, uv-coordinates and distance for the pre-synaptic neuron
        pre_p3d, pre_p2d, pre_d = computeMapping(layers[0:(slayer+1)],
                                                 connections[0:slayer],
                                                 distances[0:slayer],
                                                 layers[0].particle_systems[neuronset1].particles[i].location)

        for j in range(0, len(layers[-1].particle_systems[neuronset2].particles)):
            # compute position, uv-coordinates and distance for the post-synaptic neuron
            post_p3d, post_p2d, post_d = computeMapping(layers[:(slayer-1):-1],
                                                        connections[:(slayer-1):-1],
                                                        distances[:(slayer-1):-1],
                                                        layers[-1].particle_systems[neuronset2].particles[j].location)

            # determine connectivity probabiltiy and distance values
            conn[i, j] = computeConnectivityProbability(pre_p2d * layers[slayer]['uv_scaling'], post_p2d * layers[slayer]['uv_scaling'], func, args)
            # for euclidean distance
            if distances[slayer-1] == 0:
                dist[i, j] = pre_d + post_d + (post_p3d[-1] - pre_p3d[-2]).length
            # for normal-uv-distance
            elif  distances[slayer-1] == 1:
                dist[i, j] = pre_d + post_d + (post_p2d - pre_p2d).length * layers[slayer]['uv_scaling']
            # for euclidean-uv-distances
            elif distances[slayer-1] == 2:
                dist[i, j] = pre_d + post_d + (post_p2d - pre_p2d).length * layers[slayer]['uv_scaling']
                
    return conn, dist


#def computeConnectivity(l1, p1, l2, p2, al, l1t, l2t, func, args):
#    """computes the connectivity probability between two layers l1 and l2 using
#    an axon layer al
#    l1, l2      : layers with neuronsets (with particlesystems)
#    p1, p2      : name of the neuronsets (particlesystems)
#    al          : axon layer
#    l1t, l2t    : 1, if topologically identical with al, 0, if not '''
#
#    result = np.zeros((len(l1.particle_systems[p1].particles), len(l2.particle_systems[p2].particles)))
#    
#    # go through all neurons of l1 
#    for i in range(0, len(l1.particle_systems[p1].particles)):
#        # get uv-coordinates of the neuron on al-layer
#        if l1t == 1:
#            a_uv_l1 = map3dPointToUV(l1, al, l1.particle_systems[p1].particles[i].location)
#        else: 
#            a_uv_l1 = map3dPointToUV(al, al, l1.particle_systems[p1].particles[i].location)            
#
#        # go through all neurons of l2
#        for j in range(0, len(l2.particle_systems[p2].particles)):
#            # get uv-coordinate of the neuron on al-layer        
#            if l2t == 1:
#                a_uv_l2 = map3dPointToUV(l2, al, l2.particle_systems[p2].particles[j].location)
#            else:
#                a_uv_l2 = map3dPointToUV(al, al, l2.particle_systems[p2].particles[j].location)
#            
#            result[i, j] = computeConnectivityProbability(a_uv_l1, a_uv_l2, func, args)   
#            
#    return result


def initialize3D():
    """prepares all necessary steps for the computation of connections"""

    # compute the UV scaling factor for all layers that have UV-maps
    for o in bpy.data.objects:
        if o.type == 'MESH':
            if len(o.data.uv_layers) > 0:
                o['uv_scaling'] = computeUVScalingFactor(o)


def test():
    """ Just a routine to perform some tests """
    initialize3D()
    pv.visualizeClean()
    
    t1 = bpy.data.objects['t1']
    t2 = bpy.data.objects['t2']
    t201 = bpy.data.objects['t2.001']
    t3 = bpy.data.objects['t3']
    t4 = bpy.data.objects['t4']
    t5 = bpy.data.objects['t5']
	
    point, n, p = t1.closest_point_on_mesh(pv.getCursor())
	

    p3, p2, d = computeMapping([t1, t2, t201, t3, t4, t5], [1, 0, 1, 1, 1], [0, 0, 0, 0, 0], point)
    print(p3)
    print(p2)
    print(d)
	
    pv.visualizePath(p3)
    
    
def hippotest():
    """ A routine to test the functionality on a hippocampus-like shape """    
    dg = bpy.data.objects['DG_sg']
    ca3 = bpy.data.objects['CA3_sp']
    ca1 = bpy.data.objects['CA1_sp']
    al_dg = bpy.data.objects['DG_sg_axons_all']
    al_ca3 = bpy.data.objects['CA3_sp_axons_all']
    
    # preparatory steps are done in initialize3D (e.g. calculating the uv-scaling-factor for all
    # meshs with uv-data.
    print('Initialize data')
    initialize3D()
    
    # connect ca3 with ca3 using an intermediate layer al_ca3. first relationship is topological,
    # second one is euclidian
    # use a gauss-function with given variance and shifting parameters to determine the connectivity
    
    params = [10., 3., 7., 0.00]
    
    print('Compute Connectivity for ca3 to ca1')
    c_ca3_ca3, d_ca3_ca3 = computeConnectivity([ca3, al_ca3, ca3],                      # layers involved in the connection
                                                'CA3_Pyramidal', 'CA3_Pyramidal',       # neuronsets involved
                                                1,                                      # synaptic layer
                                                [1, 0],                                 # connection mapping
                                                [1, 0],                                 # distance calculation
                                                connfunc_gauss, params)   # kernel function plus parameters                                               
        
    print('Compute Connectivity for ca3 to ca1')
    c_ca3_ca1, d_ca3_ca1 = computeConnectivity([ca3, al_ca3, ca1],                      # layers involved in the connection
                                               'CA3_Pyramidal', 'CA1_Pyramidal',       # neuronsets involved
                                               1,                                      # synaptic layer
                                               [1, 0],                                 # connection mapping
                                               [1, 0],                                 # distance calculation
                                               connfunc_gauss, params)   # kernel function plus parameters
    
    
    
	#c_ca3_ca1 = computeConnectivity(ca3, 'CA3_Pyramidal', ca1, 'CA1_Pyramidal', al_ca3, 1, 0, connfunc_gauss, [3.0, 0.3, 2.3, 0.00])
    
	## the rest is just for visualization
    pv.visualizeClean()
    
    particle = 44
    
    pv.setCursor(ca3.particle_systems['CA3_Pyramidal'].particles[particle].location)
    
    pv.visualizePostNeurons(ca3, 'CA3_Pyramidal', c_ca3_ca3[particle])
    pv.visualizePostNeurons(ca1, 'CA1_Pyramidal', c_ca3_ca1[particle])
    

if __name__ == "__main__":
    ##############################################################################################
    ## Main Code:
    ## Here the connectivity between two layers using an intermediate layer
    ##############################################################################################

    test() 
    #hippotest()
       

